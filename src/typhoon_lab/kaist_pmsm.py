"""Native measurements and provenance for the KAIST PMSM v5 publication."""

from collections import defaultdict
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import numpy as np

from .utils import sha256


DATASET_DOI = "10.17632/rgn5brrgrn.5"
ARCHIVES = {1000: "1.0kW.zip", 1500: "1.5kW.zip", 3000: "3.0kW.zip"}
LABELS = ("healthy", "interturn", "intercoil")
WINDOW_STARTS_S = (10, 30, 60, 90)
WINDOW_LENGTH_S = 2
RATES_HZ = {"current": 100_000, "vibration": 25_600}
CURRENT_FUNDAMENTAL_BAND_HZ = (195, 205)
OBSERVATIONS = {
    "I0": ["current_crest_factor", "current_rms_window_cv"],
    "Q1": ["phase_rms_cv", "sequence_minor_major"],
    "Q2": ["current_h3_ratio", "current_h5_ratio", "current_h7_ratio"],
    "Q3": ["vibration_1x_share", "vibration_2x_share", "vibration_3x_share", "vibration_4x_share"],
}
FILE_NAME = re.compile(
    r"(?P<motor>\d+)W_(?P<severity>\d+[_.]\d+)_(?P<sensor>current|vibration)_"
    r"(?P<fault>interturn|intercoil|coil)\.tdms", re.I,
)
SENSOR_LAYOUTS = {
    "current": {"channels": 3, "tdms_type": "Current", "unit": "A", "device": "NI 9775"},
    "vibration": {"channels": 1, "tdms_type": "Acceleration", "unit": "g", "device": "NI 9234"},
}


class DataIssue(ValueError):
    """A recording lacks an observation required by the registered protocol."""


def inspect_archives(source, motors=tuple(ARCHIVES)):
    """Verify publication digests and inspect member names without reading waveforms."""
    source = Path(source).resolve()
    receipt_path = source / "repository-files.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    files = {item["filename"]: item["content_details"] for item in receipt}
    if set(files) != set(ARCHIVES.values()) or len(receipt) != len(ARCHIVES):
        raise DataIssue("repository receipt must list the three KAIST v5 archives")

    inventory = {}
    for motor in motors:
        filename = ARCHIVES[motor]
        archive = source / filename
        item = files[filename]
        if archive.stat().st_size != item["size"] or sha256(archive) != item["sha256_hash"]:
            raise DataIssue(f"publication size or SHA-256 differs for {filename}")
        groups = defaultdict(lambda: {"current": [], "vibration": []})
        seen = set()
        with ZipFile(archive) as bundle:
            for info in bundle.infolist():
                name = PurePosixPath(info.filename)
                if name.suffix.lower() != ".tdms":
                    continue
                match = FILE_NAME.fullmatch(name.name)
                if not match or int(match["motor"]) != motor or info.filename in seen:
                    raise DataIssue(f"unexpected TDMS member in {filename}: {info.filename}")
                seen.add(info.filename)
                severity = match["severity"].replace("_", ".")
                label = "intercoil" if match["fault"].lower() == "coil" else match["fault"].lower()
                if float(severity) == 0:
                    label = "healthy"
                groups[label, severity][match["sensor"].lower()].append({
                    "member": info.filename, "bytes": info.file_size, "crc32": f"{info.CRC:08x}",
                })
        inventory[str(motor)] = {
            "archive": filename, "sha256": item["sha256_hash"], "archive_bytes": item["size"],
            "tdms_members": len(seen),
            "conditions": [
                {"label": label, "severity_pct": severity, **sensors}
                for (label, severity), sensors in sorted(groups.items())
            ],
        }
    return {"doi": DATASET_DOI, "receipt_sha256": sha256(receipt_path), "motors": inventory}


def _waveform_clock(channel, rate):
    props = channel.properties
    if props.get("wf_xunit_string") != "s":
        raise DataIssue(f"{channel.path} does not use a time axis in seconds")
    try:
        interval = float(props["wf_increment"])
        offset = float(props["wf_start_offset"])
        origin = props["wf_start_time"]
    except (KeyError, TypeError, ValueError) as exc:
        raise DataIssue(f"{channel.path} has incomplete NI waveform timing metadata") from exc
    if not math.isclose(interval, 1 / rate, rel_tol=1e-6) or not math.isfinite(offset):
        raise DataIssue(f"{channel.path} does not support the published {rate} Hz sampling rate")
    return {"origin_as_stored": str(origin), "offset_s": offset, "interval_s": interval}


def _band_power(spectra, center_hz, half_width_hz=2):
    bins = np.arange(spectra.shape[-1])
    band = np.abs(bins / WINDOW_LENGTH_S - center_hz) <= half_width_hz
    return float(spectra[..., band].sum())


def _current_features(values):
    phase_rms = np.sqrt(np.mean(values ** 2, axis=1))
    mean_rms = float(phase_rms.mean())
    pooled_rms = float(np.sqrt(np.mean(values ** 2)))
    if mean_rms <= 0:
        raise DataIssue("no current amplitude in a registered window")
    centered = values - values.mean(axis=1, keepdims=True)
    fft = np.fft.rfft(centered * np.hanning(values.shape[1]), axis=1)
    power = np.abs(fft) ** 2
    band_start, band_end = CURRENT_FUNDAMENTAL_BAND_HZ
    bins = np.arange(band_start * WINDOW_LENGTH_S, band_end * WINDOW_LENGTH_S + 1)
    fundamental_bin = bins[np.argmax(power[:, bins].sum(axis=0))]
    hz = fundamental_bin / WINDOW_LENGTH_S
    rotation = np.exp(2j * np.pi / 3)
    abc = fft[:, fundamental_bin]
    positive = abs(abc @ np.array([1, rotation, rotation ** 2]))
    negative = abs(abc @ np.array([1, rotation ** 2, rotation]))
    fundamental = _band_power(power, hz)
    low_frequency_power = float(power[:, 20 * WINDOW_LENGTH_S:1000 * WINDOW_LENGTH_S + 1].sum())
    if low_frequency_power <= 0 or fundamental < 0.01 * low_frequency_power or max(positive, negative) <= 0:
        raise DataIssue("no resolvable current fundamental in a registered window")
    return {
        "pooled_rms_a": pooled_rms,
        "electrical_fundamental_hz": hz,
        "electrical_fundamental_low_band_share": fundamental / low_frequency_power,
        "current_crest_factor": np.max(np.abs(values)) / pooled_rms,
        "phase_rms_cv": phase_rms.std() / mean_rms,
        "sequence_minor_major": min(positive, negative) / max(positive, negative),
        **{
            f"current_h{order}_ratio": math.sqrt(_band_power(power, order * hz) / fundamental)
            for order in (3, 5, 7)
        },
    }


def _vibration_features(values):
    centered = values - values.mean()
    power = np.abs(np.fft.rfft(centered * np.hanning(values.size))) ** 2
    total = float(power[10 * WINDOW_LENGTH_S:1000 * WINDOW_LENGTH_S + 1].sum())
    if total <= 0:
        raise DataIssue("no vibration energy in the registered frequency band")
    return {
        f"vibration_{order}x_share": _band_power(power, order * 50) / total
        for order in (1, 2, 3, 4)
    }


def _read_sensor(path, sensor):
    from nptdms import TdmsFile

    rate = RATES_HZ[sensor]
    layout = SENSOR_LAYOUTS[sensor]
    with TdmsFile.open(path) as tdms:
        channels = [channel for group in tdms.groups() for channel in group.channels()]
        signals = sorted(channels, key=lambda channel: channel.path)
        if len(signals) != layout["channels"] or any(
            signal.properties.get("DAC~Channel~Type") != layout["tdms_type"]
            or signal.properties.get("DAC~Device~Name") != layout["device"]
            or signal.properties.get("unit_string") != layout["unit"] for signal in signals
        ):
            raise DataIssue(f"{sensor} does not match the published NI device, channel count, or unit")
        clocks = [_waveform_clock(signal, rate) for signal in signals]
        samples = len(signals[0])
        if any(clock != clocks[0] for clock in clocks) or any(len(signal) != samples for signal in signals):
            raise DataIssue(f"{sensor} channels do not share time metadata and sample count")
        interval = clocks[0]["interval_s"]
        windows = []
        for start in WINDOW_STARTS_S:
            first = round(start / interval)
            stop = first + WINDOW_LENGTH_S * rate
            if stop > samples:
                raise DataIssue(f"{sensor} does not cover a registered window at {start}s")
            data = np.stack([signal[first:stop] for signal in signals]).astype(float, copy=False)
            if not np.isfinite(data).all():
                raise DataIssue(f"{sensor} contains nonfinite samples at {start}s")
            metrics = _current_features(data) if sensor == "current" else _vibration_features(data[0])
            windows.append({
                "indices": [first, stop],
                "seconds_from_record_start": [first * interval, (stop - 1) * interval],
                "metrics": {key: float(value) for key, value in metrics.items()},
            })
    return {
        "time_source": "NI waveform properties", "clock": clocks[0], "sample_count": samples,
        "last_relative_second": (samples - 1) * interval, "sample_rate_hz": rate,
        "channels": [{"channel": signal.path, "unit": layout["unit"], "device": layout["device"]}
                     for signal in signals],
        "windows": windows,
    }


def _materialize_group(bundle, group, scratch):
    sensors = {}
    for sensor in RATES_HZ:
        original = group[sensor]
        if not original:
            raise DataIssue(f"missing {sensor} member")
        aliases = []
        member_copy = scratch / f"{sensor}.tdms"
        for index, member in enumerate(original):
            target = member_copy if index == 0 else scratch / f"{sensor}_alias.tdms"
            with bundle.open(member["member"]) as readable, target.open("wb") as writable:
                shutil.copyfileobj(readable, writable, length=2 ** 20)
            aliases.append({**member, "sha256": sha256(target)})
        if len({alias["sha256"] for alias in aliases}) != 1:
            raise DataIssue(f"{sensor} aliases for one condition are distinct and cannot be paired by filename")
        sensors[sensor] = {"members": aliases, **_read_sensor(member_copy, sensor)}
    return sensors


def read_recordings(source, inventory, motors, workdir):
    """Extract one condition at a time. Keep sources byte-identical."""
    valid, excluded = [], []
    with TemporaryDirectory(prefix="tdms-", dir=workdir) as tmp:
        for motor in motors:
            archive = inventory["motors"][str(motor)]
            with ZipFile(Path(source) / archive["archive"]) as bundle:
                for group in archive["conditions"]:
                    origin = {"motor_w": motor, "label": group["label"], "severity_pct": group["severity_pct"]}
                    try:
                        sensors = _materialize_group(bundle, group, Path(tmp))
                    except DataIssue as exc:
                        excluded.append({**origin, "reason": str(exc)})
                        continue
                    metrics = {}
                    for metadata in sensors.values():
                        rows = [item["metrics"] for item in metadata["windows"]]
                        metrics.update({key: float(np.median([row[key] for row in rows])) for key in rows[0]})
                    rms = np.array([row["metrics"]["pooled_rms_a"] for row in sensors["current"]["windows"]])
                    metrics["current_rms_window_cv"] = float(rms.std() / rms.mean())
                    observations = {
                        bundle_id: {feature: metrics[feature] for feature in features}
                        for bundle_id, features in OBSERVATIONS.items()
                    }
                    valid.append({**origin, "sensors": sensors, "observations": observations})
            print(f"实测归档 {motor} W：{sum(row['motor_w'] == motor for row in valid)} 个合格采集条件",
                  flush=True)
    by_hash = defaultdict(list)
    for row in valid:
        for sensor in RATES_HZ:
            by_hash[row["sensors"][sensor]["members"][0]["sha256"]].append(row)
    conflicts = {id(row) for uses in by_hash.values() if len(uses) > 1 for row in uses}
    for row in valid:
        if id(row) in conflicts:
            excluded.append({
                **{key: row[key] for key in ("motor_w", "label", "severity_pct")},
                "reason": "a source waveform is byte-identical across distinct conditions",
            })
    return {
        "recordings": [row for row in valid if id(row) not in conflicts], "excluded": excluded,
    }
