"""Prediction order, missing observations, privacy and numerical replay."""
from copy import deepcopy
import csv
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from typhoon_lab.diagnostic_tools import UNITS, ObservationTools, check_prediction
from typhoon_lab.pmsm_diagnosis import prepare_dataset, public_packet, read, run_diagnosis, verify_diagnosis, fixed_reference, difference_evidence, open_case, evaluate_session, review_session
from typhoon_lab.pmsm_feedback_review import assess
from typhoon_lab.utils import finalize, write_json, sha256


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.data={'time_s':np.arange(80)/100}
        self.data.update({key:np.zeros(80) for key in UNITS})
        self.data['model_speed_rpm'][:]=2250
        self.data['controller_speed_rpm'][:]=2400
        self.data['reference_speed_rpm'][:]=2400
        self.tools=ObservationTools(self.data,UNITS)

    def test_difference_sign_and_units_are_explicit(self):
        args={'left':'controller_speed_rpm','right':'model_speed_rpm','window_s':[.5,.6]}
        result=self.tools.execute('difference',args)
        self.assertEqual(result['mean_difference'],150)
        prediction={'hypothesis_id':'H1','metric':'mean_difference','expected_interval':[0,10]}
        self.assertEqual(check_prediction(prediction,result)['status'],'outside')
        args['left']='load_nm'
        self.assertEqual(self.tools.execute('difference',args)['status'],'invalid_query')

    def test_hidden_signal_is_unavailable_not_zero_and_prediction_is_not_refuted(self):
        tools=ObservationTools(self.data,set(UNITS)-{'controller_speed_rpm'})
        result=tools.execute('difference',{'left':'controller_speed_rpm','right':'model_speed_rpm','window_s':[.5,.6]})
        self.assertEqual(result['status'],'unavailable')
        prediction={'hypothesis_id':'H1','metric':'mean_difference','expected_interval':[0,10]}
        self.assertEqual(check_prediction(prediction,result)['status'],'not_assessable')
        self.assertFalse(tools.execute('availability',{'channels':['current_limit_flag']})['available']['current_limit_flag'])

    def test_bad_window_and_non_signal_requests_do_not_read_files(self):
        for window in [[.5,.5],[-1,.1],[0,2],[True,.7]]:
            self.assertEqual(self.tools.execute('statistics',{'channels':['model_speed_rpm'],'window_s':window})['status'],'invalid_query')
        self.assertEqual(self.tools.execute('availability',{'channels':['../../private.json']})['status'],'invalid_query')
        self.assertEqual(self.tools.execute('read_file',{'path':'private.json'})['status'],'invalid_query')


class DiagnosisReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'results').mkdir()
        self.patcher=patch('typhoon_lab.pmsm_diagnosis.PROJECT',self.root)
        self.patcher.start();self.addCleanup(self.patcher.stop)
        sources=[]
        for label,bias in [('private-normal-token',0),('private-fault-token',150)]:
            source=self.root/'results'/label;source.mkdir();sources.append(source)
            config={'model':'pmsm_feedback_probe','parameters':{'reference_speed_rpm':1800},
                    'fault':{'kind':'speed_feedback_bias','at_s':.4,'bias_rpm':bias}}
            write_json(source/'config.json',config)
            write_json(source/'manifest.json',{})
            write_json(source/'capture.json',{})
            write_json(source/'metrics.json',{'fault_observation':{'injection_verified':True},
                       'events':[{'target':'reference_speed_rpm','observed_at_s':.2,'value':2400}]})
            with (source/'waveforms.csv').open('w',encoding='utf-8',newline='') as f:
                writer=csv.writer(f);writer.writerow(['t_simulation_s','MechanicalSpeed_rad_s','SpeedFeedback_rad_s',
                    'Reference_rad_s','Load_Nm','ElectromagneticTorque_Nm','Ia_A','Ib_A','Ic_A','FeedbackBias_rad_s'])
                for i in range(80):
                    t=i/100;ref=1800 if t<.2 else 2400;b=bias if t>=.4 else 0
                    writer.writerow([t,(ref-b)*math.pi/30,ref*math.pi/30,ref*math.pi/30,.01,.01,0,0,0,b*math.pi/30])
        self.dataset=self.root/'results/dataset'
        with patch('typhoon_lab.records.verify_run',return_value={'record_status':'passed','experiment_status':'passed'}):
            prepare_dataset(self.dataset,*sources)
        truth=read(self.dataset/'private.json')['truth']
        self.full=next(k for k,v in truth.items() if v['expected_finding']=='feedback_path_discrepancy')
        self.masked=next(k for k,v in truth.items() if v['masked_feedback'])

    def provider(self,answers):
        responses=iter(answers)
        def call(folder,service,system,request):
            serialized=json.dumps(request,ensure_ascii=False)
            for hidden in ['private-normal-token','private-fault-token','FeedbackBias_rad_s','hidden_fault','expected_finding']:
                self.assertNotIn(hidden,serialized)
            answer=next(responses);folder=Path(folder);folder.mkdir()
            write_json(folder/'input.json',request)
            write_json(folder/'http_request.json',{'messages':[{'role':'system','content':system},{'role':'user','content':serialized}]})
            write_json(folder/'answer.json',answer)
            write_json(folder/'http_response.json',{'choices':[{'message':{'content':json.dumps(answer,ensure_ascii=False)},'finish_reason':'stop'}]})
            return answer
        return call

    def decisions(self,finding):
        query={'analysis':'先检查两测点差异以区分候选。','hypotheses':[{'id':'H1','claim':'两测点无偏差','status':'candidate','support':['I0'],'conflict':[]}],
            'action':{'type':'query','tool':'difference','arguments':{'left':'controller_speed_rpm','right':'model_speed_rpm','window_s':[.5,.6]},
            'prediction':{'hypothesis_id':'H1','metric':'mean_difference','expected_interval':[-2,2],'rationale':'检查候选的零偏差预测'}}}
        finish={'analysis':'根据返回证据修正判断，缺失观测时保留未决。',
            'hypotheses':[{'id':'H1','claim':'两测点无偏差','status':'weakened' if finding=='feedback_path_discrepancy' else 'unresolved','support':[],'conflict':['Q1'] if finding=='feedback_path_discrepancy' else []}],
            'action':{'type':'finish','finding':finding,'supported_by':['I0','Q1'],'limiter_state':'unobserved','remaining_gaps':['其他机制仍需核验']}}
        return [query,finish]

    def test_query_prediction_conflict_and_update_replay_without_hidden_truth(self):
        case=next(c for c in read(self.dataset/'public_cases.json') if c['case_id']==self.full)
        self.assertEqual(case['initial_observation']['left_channel'],'model_speed_rpm')
        self.assertEqual(case['initial_observation']['right_channel'],'reference_speed_rpm')
        self.assertEqual(case['initial_observation']['definition'],'model_speed_rpm minus reference_speed_rpm')
        output=self.root/'results/session'
        with patch('typhoon_lab.pmsm_diagnosis.call_json',side_effect=self.provider(self.decisions('feedback_path_discrepancy'))):
            result=run_diagnosis(output,self.dataset,self.full,'unused')
        self.assertEqual(result['status'],'passed')
        self.assertEqual(read(output/'turn-01/tool_result.json')['response']['prediction_check']['status'],'outside')
        self.assertEqual(verify_diagnosis(output)['record_status'],'passed')
        manifest=read(output/'manifest.json');manifest['steps'][0]['tool']['result']['mean_difference']=0
        write_json(output/'turn-01/tool_result.json',{'response':manifest['steps'][0]['tool'],'monotonic_ns':10**30})
        finalize(output,manifest)
        self.assertIn('tool result or pre-query prediction differs',verify_diagnosis(output)['record_problems'])

    def test_fixed_reference_uses_only_available_observations(self):
        self.assertEqual(fixed_reference(self.dataset,self.full)['finding'],'feedback_path_discrepancy')
        masked=fixed_reference(self.dataset,self.masked)
        self.assertEqual(masked['finding'],'undetermined')
        self.assertEqual(masked['query_count'],0)

    def test_equivalent_differences_require_matching_windows_and_cited_evidence(self):
        case,tools=open_case(self.dataset,self.full)
        args={'left':'controller_speed_rpm','right':'reference_speed_rpm','window_s':[.6,.7]}
        result=tools.execute('difference',args)
        steps=[{'tool':{'tool':'difference','arguments':args,'result':result,'evidence_id':'Q1'}}]
        proof=difference_evidence(case,steps,{'I0','Q1'})
        self.assertAlmostEqual(proof['controller_minus_model_rpm'],150)
        self.assertEqual(proof['type'],'derived_same_window')
        self.assertIsNone(difference_evidence(case,steps,{'Q1'}))
        steps[0]['tool']['result']['window_s']=[.5,.6]
        self.assertIsNone(difference_evidence(case,steps,{'I0','Q1'}))

    def test_review_keeps_original_trace_and_original_failed_evaluation(self):
        source=self.root/'results/equivalent'
        answers=self.decisions('feedback_path_discrepancy')
        answers[0]['action']['arguments']['right']='reference_speed_rpm'
        answers[0]['action']['arguments']['window_s']=[.6,.7]
        with patch('typhoon_lab.pmsm_diagnosis.call_json',side_effect=self.provider(answers)):
            result=run_diagnosis(source,self.dataset,self.full,'unused')
        self.assertEqual(result['status'],'passed')
        m=read(source/'manifest.json');m['evaluation_version']=1
        m['evaluation']=evaluate_session(self.dataset,self.full,m['steps'],1);m['status']='failed'
        write_json(source/'evaluation.json',m['evaluation']);finalize(source,m)
        original_hash=sha256(source/'manifest.json')
        self.assertEqual(verify_diagnosis(source)['record_status'],'passed')
        reviewed=self.root/'results/reviewed'
        result=review_session(reviewed,source)
        self.assertEqual(result['status'],'passed')
        self.assertEqual(sha256(source/'manifest.json'),original_hash)
        self.assertEqual(read(reviewed/'original-evaluation.json')['status'],'failed')
        self.assertEqual(read(reviewed/'manifest.json')['steps'],m['steps'])

    def test_missing_feedback_preserves_undetermined_result(self):
        output=self.root/'results/masked'
        with patch('typhoon_lab.pmsm_diagnosis.call_json',side_effect=self.provider(self.decisions('undetermined'))):
            result=run_diagnosis(output,self.dataset,self.masked,'unused')
        self.assertEqual(result['status'],'passed')
        self.assertEqual(read(output/'turn-01/tool_result.json')['response']['prediction_check']['status'],'not_assessable')

    def test_wrong_model_finding_does_not_become_a_record_failure(self):
        output=self.root/'results/wrong'
        finish=self.decisions('normal_response')[1];finish['action']['supported_by']=['I0'];finish['hypotheses']=[]
        with patch('typhoon_lab.pmsm_diagnosis.call_json',side_effect=self.provider([finish])):
            result=run_diagnosis(output,self.dataset,self.full,'unused')
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['record_status'],'passed')
        self.assertEqual(result['workflow_status'],'completed')

    def test_projection_forgery_is_detected_even_if_package_hashes_are_refreshed(self):
        case=next(c for c in read(self.dataset/'public_cases.json') if c['case_id']==self.full)
        path=self.dataset/case['observation_file']
        text=path.read_text(encoding='utf-8');lines=text.splitlines();fields=lines[-1].split(',');fields[1]='0';lines[-1]=','.join(fields)
        path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        finalize(self.dataset,read(self.dataset/'manifest.json'))
        self.assertIn('projection differs from original waveform: model_speed_rpm',verify_diagnosis(self.dataset)['record_problems'])


class FeedbackReviewTests(unittest.TestCase):
    def test_arithmetic_and_unobserved_state_are_separate_checks(self):
        expected={'margin_A_ms':85.8,'margin_B_ms':77.8,'smaller_margin_case':'B','lower_iae_case':'B',
                  'main_prediction_within':False,'limiter_established':False,'needs_limiter_observation':True}
        answer={**expected,'interpretation_update':'余量与积分分别解释，限幅状态未观测。'}
        self.assertEqual(assess(answer,expected)['status'],'passed')
        answer['limiter_established']=True
        self.assertFalse(assess(answer,expected)['checks']['limiter_established'])
        self.assertTrue(assess(answer,expected)['checks']['margin_A_ms'])


if __name__=='__main__':unittest.main()
