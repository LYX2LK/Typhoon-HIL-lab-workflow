"""Build local-only Virtual HIL teaching files using the THCC 2026.3 Python."""

from copy import deepcopy
import json
import math
from pathlib import Path
from shutil import copyfile
import sys
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))

from typhoon.api.schematic_editor import SchematicAPI
from typhoon_lab.pmsm_preview import PMSMPreviewAdapter
from typhoon_lab.runtime import installation, require
from typhoon_lab.utils import sha256


NAME = 'tle9877_gui_practice'
PANEL_SOURCE_SHA256 = '9608edee87288eb8dc1ebe0588413d5affa0e4b31c9af2d421704814180e2e99'
PRESETS = (
    ('01 Start', 'Reference_rpm', 'Rising', 900),
    ('02 Speed step', 'Reference_rpm', 'Rising', 2100),
    ('03 Load step', 'LabLoad', 'Rising', 0.02),
    ('04 Zero speed', 'Reference_rpm', 'Falling', 1200),
)
SIGNALS = (
    ('Reference_rpm', 1), ('Speed_rpm', 1), ('SpeedError_rpm', 2),
    ('Ia', 3), ('Ib', 3), ('Ic', 3), ('LabLoad', 4), ('LabTorque', 4),
)


def build_model(source, target, config):
    api = SchematicAPI()
    adapter = PMSMPreviewAdapter()
    config = adapter.validate(config)
    parameters = {**config['parameters'], 'reference_speed_rpm': 0}
    require(api.load(filename=str(source)), 'load the official PMSM example')
    try:
        adapter.prepare_model(api, parameters, (), config['assumptions'])
        for name, position in (('LabReference', (6952, 7784)), ('LabLoad', (7664, 6640))):
            api.set_position(api.get_item(name), position)

        def add(kind, name, position, **properties):
            component = api.create_component(f'core/{kind}', name=name, position=position)
            api.set_property_values(component, properties)
            return component

        def wire(start, end):
            if not api.create_connection(start, end):
                raise RuntimeError('Could not connect the GUI measurement branch')

        ref_gain = add('Gain', 'ReferenceScale', (7136, 7920), gain=str(30 / math.pi), execution_rate='Ts')
        speed_gain = add('Gain', 'SpeedScale', (7136, 8000), gain=str(30 / math.pi), execution_rate='Ts')
        wire(api.term(api.get_item('w_ref'), 'out'), api.term(ref_gain, 'in'))
        wire(api.get_item('Junction236'), api.term(speed_gain, 'in'))
        error = add('Sum', 'SpeedMinusReference', (7376, 7976), signs='+-', execution_rate='Ts')
        wire(api.term(speed_gain, 'out'), api.term(error, 'in'))
        wire(api.term(ref_gain, 'out'), api.term(error, 'in1'))
        for name, origin, position in (
            ('Reference_rpm', ref_gain, (7280, 7872)),
            ('Speed_rpm', speed_gain, (7280, 8056)),
            ('SpeedError_rpm', error, (7520, 7976)),
        ):
            probe = add('Probe', name, position)
            wire(api.term(origin, 'out'), api.term(probe, 'in'))
        require(api.save_as(filename=str(target)), 'save the GUI practice schematic')
    finally:
        api.close_model()


def set_fields(element, **values):
    for tag, value in values.items():
        child = element.find(tag)
        if child is None:
            child = ET.SubElement(element, tag)
        child.text = str(value)


def set_signals(settings):
    signals = settings.find('analog_signals')
    template = deepcopy(signals[0])
    signals.clear()
    for channel, (name, viewport) in enumerate(SIGNALS):
        row = deepcopy(template)
        set_fields(row, channel=channel, name=name)
        set_fields(row.find('viewports'), num_viewport=viewport)
        signals.append(row)


def configure_capture(capture, source, edge, threshold):
    set_signals(capture)
    set_fields(capture, time_interval=0.4, sample_rate=100000.0)
    set_fields(capture.find('trigger'), type='Analog', source=source, edge=f'{edge} edge',
               treshold=threshold, offset=25.0, useFirstTrigger=False, is_force=False)


def build_panel(source, target):
    example = ET.parse(source).getroot()
    capture = next(widget for widget in example.find('components') if widget.findtext('type') == 'Capture/Scope')
    root = ET.Element('ui_settings')
    set_fields(root, version=example.findtext('version'), model_locked=False, canvas_bg_color='#ffffff',
               initialization_code=("for ok in (hil.set_source_constant_value('V_dc', value=9.0),\n"
                                    "           hil.set_scada_input_value('w_ref', 0.0),\n"
                                    "           hil.set_scada_input_value('load_torque', 0.01)):\n"
                                    "    if ok is not True:\n"
                                    "        raise RuntimeError('Practice initialization failed')\n"))
    widgets = ET.SubElement(root, 'components')
    for index, (label, signal, value) in enumerate((
        ('1800 rpm', 'w_ref', 1800 * math.pi / 30),
        ('2400 rpm', 'w_ref', 2400 * math.pi / 30),
        ('Load 0.03 Nm', 'load_torque', 0.03),
        ('Zero speed', 'w_ref', 0.0),
    ), start=1):
        button = ET.SubElement(widgets, 'component_data')
        set_fields(button, id=f'{index:032x}', name=label, type='MacroButton', description='',
                   on_start_code_source='Custom code')
        ET.SubElement(button, 'on_use_code', active='True').text = (
            f"if hil.set_scada_input_value({signal!r}, {value!r}) is not True:\n"
            f"    raise RuntimeError('Could not apply {label}')\n"
        )
        ET.SubElement(button, 'on_start_code', active='False')
        ET.SubElement(button, 'on_stop_code', active='False')
        settings = ET.SubElement(button, 'widget_settings')
        set_fields(settings, x=16 + (index - 1) * 168, y=8, width=152, height=32,
                   appearance='Flat', hierarchy_position=1, is_background=False, label='', use_label=False)

    set_fields(capture, working_mode='embedded')
    settings = capture.find('widget_settings')
    set_fields(settings, x=8, y=48, width=992, height=648)
    presets = settings.find('presets')
    template = presets.find('capture')
    presets.remove(template)
    for name, signal, edge, threshold in PRESETS:
        item = deepcopy(template)
        item.set('name', name)
        configure_capture(item, signal, edge, threshold)
        presets.append(item)
    name, signal, edge, threshold = PRESETS[0]
    set_fields(presets, active_capture_preset=name)
    configure_capture(settings.find('capture'), signal, edge, threshold)
    for scope in (settings.find('scope'), presets.find('scope')):
        set_signals(scope)
        set_fields(scope.find('trigger'), type='Analog', source=signal, edge='Rising edge', treshold=threshold)
    widgets.append(capture)
    ET.indent(root)
    with target.open('xb') as output:
        ET.ElementTree(root).write(output, encoding='utf-8', xml_declaration=True)


def main():
    models = PROJECT / 'models'
    origin = json.loads((models / 'origin.json').read_text(encoding='utf-8'))['pmsm_software_preview']
    home = installation()
    source = home / origin['installation_relative_path']
    panel = source.with_suffix('.cus')
    if ((home / '.version').read_text(encoding='utf-8').strip() != origin['thcc_version']
            or sha256(source) != origin['sha256'] or sha256(panel) != PANEL_SOURCE_SHA256):
        raise ValueError('Installed PMSM example or panel does not match the registered THCC 2026.3 source')
    model_target, panel_target = (models / f'{NAME}.{suffix}' for suffix in ('tse', 'cus'))
    for target in (model_target, panel_target):
        if target.exists():
            raise FileExistsError(f'Keep or move the existing practice file before preparing a fresh copy: {target}')
    config = json.loads((PROJECT / 'configs/pmsm_software_preview.json').read_text(encoding='utf-8'))
    with TemporaryDirectory(prefix='tle9877-gui-', dir=models) as folder:
        staging = Path(folder)
        source_copy = staging / source.name
        copyfile(source, source_copy)
        staged_model = staging / model_target.name
        staged_panel = staging / panel_target.name
        build_model(source_copy, staged_model, config)
        build_panel(panel, staged_panel)
        staged_model.rename(model_target)
        try:
            staged_panel.rename(panel_target)
        except OSError:
            model_target.unlink()
            raise
    for target in (model_target, panel_target):
        print(f'{sha256(target)}  {target}')


if __name__ == '__main__':
    main()
