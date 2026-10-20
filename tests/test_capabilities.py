"""The static capability contract must agree with accepted configurations."""
import json
from pathlib import Path
import unittest

from typhoon_lab.adapters import describe_capabilities, get_adapter
from typhoon_lab.config import validate_config


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = (
    "rlc_baseline.json",
    "rectifier_baseline.json",
    "boost_baseline.json",
    "im_speed_1430.json",
    "im_speed_step_1430_to_850.json",
)


class CapabilityTests(unittest.TestCase):
    def test_declared_numeric_fields_cover_valid_examples(self):
        for filename in EXAMPLES:
            with self.subTest(filename=filename):
                config = json.loads((ROOT / "configs" / filename).read_text(encoding="utf-8"))
                adapter = get_adapter(config["model"])
                capabilities = describe_capabilities(adapter)
                normalized = validate_config(config)
                self.assertEqual(capabilities["configuration_schema_version"], config["schema_version"])
                for group, fields in capabilities["configuration_fields"].items():
                    for name, spec in fields.items():
                        if spec.get("when") == "events_nonempty" and not config.get("events"):
                            self.assertNotIn(name, normalized[group])
                            continue
                        value = normalized[group][name]
                        if spec["type"] == "boolean":
                            self.assertIn(value, spec["allowed_values"])
                        else:
                            self.assertLessEqual(spec["minimum"], value)
                            self.assertLessEqual(value, spec["maximum"])
                            self.assertEqual(spec["limit_source"], "current_validated_scope")
                self.assertEqual(len(capabilities["capture_signals"]), len(capabilities["signal_details"]))
                self.assertEqual(capabilities["runtime_events"], bool(capabilities["events"]["max_per_run"]))
                for event in config.get("events", []):
                    self.assertIn(event["target"], capabilities["events"]["targets"])

    def test_exposed_bound_is_enforced_by_validator(self):
        config = json.loads((ROOT / "configs" / "boost_baseline.json").read_text(encoding="utf-8"))
        lower = describe_capabilities(get_adapter(config["model"]))["configuration_fields"]["parameters"]["input_voltage_v"]["minimum"]
        config["parameters"]["input_voltage_v"] = lower / 2
        with self.assertRaises(ValueError):
            validate_config(config)


if __name__ == "__main__":
    unittest.main()
