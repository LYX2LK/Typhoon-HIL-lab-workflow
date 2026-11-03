"""Independent wire vectors and invalid-data semantics for supplied LIN.ldf."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
import tempfile
from pathlib import Path
import unittest

from typhoon_lab.cli import main
from typhoon_lab.tle9877 import (pid, checksum, decode_frame, encode_control, check_sample,
                                load_profile, DEFAULT_PROFILE)


class TLE9877Tests(unittest.TestCase):
    def test_reference_pid_and_checksum_vectors(self):
        self.assertEqual([pid(x) for x in (37,38,39,60,61)],[0x25,0xA6,0xE7,0x3C,0x7D])
        self.assertEqual(checksum(38,[0x64,0]),0xF4)
        self.assertEqual(checksum(37,[0x64,0x64,0x5A,0x50,0x0A,0,0,0]),0x5D)
        self.assertEqual(checksum(39,[1,0]),0x17)
        self.assertEqual(checksum(60,[0xFF]*8),0)
        for x in (True,-1,64,1.5):
            with self.assertRaises(ValueError): pid(x)

    def test_control_position_quantization_and_no_silent_clipping(self):
        result=encode_control(2240,5)
        self.assertEqual(result['data'],[0x64,0x50])
        self.assertIsNone(result['firmware_target_rpm'])
        self.assertEqual(encode_control(5600)['data'],[250,0])
        self.assertEqual(encode_control(5689.6)['data'],[254,0])
        self.assertEqual(encode_control(11.2)['encoded_rpm'],22.4)
        for x in (-1,5700,float('nan'),float('inf'),True):
            with self.assertRaises(ValueError): encode_control(x)
        for x in (-1,6,7,True):
            with self.assertRaises(ValueError): encode_control(2240,x)

    def test_independent_status_vector(self):
        # byte5: overtemperature; byte6: deblocking; byte7: error changed,
        # post-run stage5 and communication error. Other state bits are zero.
        s=decode_frame('status','64 64 5A 50 0A 40 40 D8')['signals']
        self.assertEqual([s[k]['value'] for k in ['Setspeed','ActualSpeed','Voltage','Temperature','Current']],
                         [2240,2240,9,30,2])
        self.assertEqual(s['ST_RPM_MONI']['label'],'rotation monitoring active')
        self.assertEqual(s['ERR_ST_OTMP']['raw'],1)
        self.assertEqual(s['ERR_ST_Block']['label'],'Deblocking active')
        self.assertEqual(s['NOD_ERR']['label'],'Status: error has changed')
        self.assertEqual(s['ST_PRM']['raw'],5)
        self.assertEqual(s['COM_ERR']['raw'],1)

    def test_invalid_undefined_initial_and_reserved_remain_distinct(self):
        d=decode_frame('status','FF FF FF FF FF FF FF FF')['signals']
        self.assertEqual(d['ActualSpeed']['validity'],'invalid')
        self.assertIsNone(d['ActualSpeed']['value'])
        self.assertEqual(d['ST_PRM']['validity'],'initial')
        self.assertEqual(d['Reserved']['validity'],'reserved')
        d=decode_frame('status','00 00 00 D3 00 08 00 60')['signals']
        self.assertEqual(d['Temperature']['validity'],'undefined')
        self.assertEqual(d['ST_RPM_MONI']['validity'],'undefined')
        self.assertEqual(d['ST_PRM']['validity'],'undefined')
        self.assertEqual(decode_frame('status','00 00 00 D2 00 00 00 00')['signals']['Temperature']['value'],160)

    def test_lengths_ids_parity_checksum_and_reserved_bits(self):
        r=decode_frame('control','64 00',identifier=0xA6,identifier_kind='pid',received_checksum=0xF4)
        self.assertTrue(r['checksum_verified'])
        self.assertTrue(decode_frame('control','64 8F')['warnings'])
        self.assertEqual(decode_frame('version','12 00')['signals']['Version']['raw'],0x12)
        for kw in ({'identifier':38,'identifier_kind':'pid'}, {'identifier':True}, {'received_checksum':0}):
            with self.assertRaises(ValueError): decode_frame('control','64 00',**kw)
        for data in ('64','64 00 00','GG 00',[256,0],[True,0]):
            with self.assertRaises(ValueError): decode_frame('control',data)

    def test_profile_readiness_units_and_schedule(self):
        r=check_sample(current_a=10)
        self.assertEqual(r['status'],'passed')
        self.assertFalse(r['sample_model_ready']);self.assertFalse(r['hardware_ready'])
        self.assertAlmostEqual(r['shunt_relation']['differential_v'],0.005)
        self.assertIsNone(r['shunt_relation']['output_voltage_command'])
        self.assertEqual(r['ldf']['schedules'][0]['cycle_s'],0.02)
        self.assertIn('pm_flux_wb',r['missing_motor_parameters'])
        self.assertEqual(r['interfaces'],18)

    def test_profile_source_drift_and_invalid_shunt_are_rejected(self):
        p,_=load_profile()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'profile.json'
            bad=deepcopy(p);bad['sources']['ldf']['sha256']='0'*64
            path.write_text(json.dumps(bad),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'snapshot'): load_profile(path)
            p['board']['shunt_resistance_ohm']=-1
            path.write_text(json.dumps(p),encoding='utf-8')
            self.assertEqual(check_sample(path)['status'],'failed')

    def test_json_entry_is_offline_and_preserves_status_semantics(self):
        out,err=io.StringIO(),io.StringIO()
        with redirect_stdout(out),redirect_stderr(err):
            code=main(['lin-encode','--rpm','2240','--json'])
        result=json.loads(out.getvalue())
        self.assertEqual(code,0)
        self.assertEqual(result['command'],'lin-encode')
        self.assertIsNone(result['experiment_status'])
        self.assertIsNone(result['record_status'])
        self.assertFalse(result['result']['sent_to_hardware'])


if __name__=='__main__': unittest.main()
