"""Offline contracts: tool use, page composition, approvals and raw evidence."""
from copy import deepcopy
import csv
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from typhoon_lab import boost_agent as agent
from typhoon_lab import boost_agent_tools as tools
from typhoon_lab.boost_agent_render import markdown,render_answer
from typhoon_lab.boost_analysis import analyze,COLUMNS
from typhoon_lab.adapters.boost import BoostAdapter
from typhoon_lab.config import load_config
from typhoon_lab.utils import PROJECT,write_json,finalize,sha256


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'agent';self.root.mkdir()
        with patch.object(agent,'new_run',return_value=self.root):self.session=agent.AgentSession()
        self.add_run('R001')

    def add_run(self,rid,event=.5,baseline=False):
        c=load_config(PROJECT/'configs/boost_vin_drop.json')
        c['capture']['duration_s']=event+1;c['acceptance']['min_samples']=round((event+1)*10000)
        c['events']=[] if baseline else [{'at_s':event,'target':'input_voltage_v','value':28.0}]
        p=self.root/'runs'/rid;p.mkdir(parents=True)
        with (p/'waveforms.csv').open('w',encoding='utf-8',newline='') as f:
            w=csv.writer(f);w.writerow(COLUMNS)
            for k in range(c['acceptance']['min_samples']):
                t=k/10000+.0000005
                y=50 if baseline else (49.5+t if t<event else 50-8*math.exp(-(t-event)/.08))
                w.writerow([k/10000,t,y,1,50,35 if baseline or t<event else 28])
        m=analyze(p/'waveforms.csv',c)
        write_json(p/'config.json',c);write_json(p/'metrics.json',m);write_json(p/'capture.json',{})
        write_json(p/'events.json',{'schema_version':2,'planned':c['events'],'events':m['events']})
        finalize(p,{'kind':'run','model':'boost_closed_loop','backend':'virtual_hil','status':m['status'],
                    'events':m['events'],'event_schedule':BoostAdapter().describe_schedule(c)})
        entry={'id':rid,'path':'runs/'+rid,'anchor_s':event,'manifest_sha256':sha256(p/'manifest.json'),
               'experiment_status':m['status'],'record_status':'passed','plan_id':None}
        self.session.state['runs'][rid]=entry;self.session.persist('fixture_run',{'id':rid})
        return entry

    def answer(self,request_hash):
        from typhoon_lab.boost_agent_investigation import context_for
        ev={k:tools.evidence_for(v,self.root) for k,v in self.session.state['runs'].items()}
        observed=context_for(ev,self.session.state['runs'],self.root)['verified_observations'][0]
        return {'request_sha256':request_hash,'assessment':{'goal':'分析当前扰动响应','decision':'continue','summary':'已有记录可用于分析。','next_requirement':'继续验证假说。',
            'claims':[observed]},'blocks':[
            {'type':'metrics','title':'模型决定先看指标','run_ids':['R001']},
            {'type':'markdown','title':'模型决定后解释','text':'候选解释需要进一步验证。','evidence':['R001.metrics']}],
            'question':{'title':'接下来如何验证？','options':[
                {'id':'delay13','label':'延后至1.3秒','description':'测试更晚施扰时的响应','recommended':True,'tool':'run_experiment',
                 'arguments':{'operation':'delay_event','reference_run':'R001','event_at_s':1.3}},
                {'id':'explain','label':'先讨论','description':'暂不运行实验','recommended':False,'tool':'discuss','arguments':{'message':'解释现有证据局限'}}]}}

    def fake_api(self,p,index,payload,service):
        if payload['tool_choice']=='none':
            a=self.answer(sha256(p/'input.json'));self._prose_answer=a
            texts=[]
            def add(value):
                if isinstance(value,str) and value.strip() and value not in texts:texts.append(value)
            for key in ('goal','summary','next_requirement'):add(a['assessment'][key])
            for c in a['assessment']['claims']:
                for key in ('claim','scope','reason','criterion','test_basis'):add(c.get(key))
            for b in a['blocks']:add(b['title']);add(b.get('text'))
            if a['question']:
                add(a['question']['title'])
                for o in a['question']['options']:
                    add(o['label']);add(o['description']);add(o['arguments'].get('message'))
            text='\n\n'.join(texts);self._prose_index=agent.index_narrative(text)
            result={'role':'assistant','content':text};finish='stop'
        else:
            name='present_report' if payload['tool_choice']=='auto' else payload['tool_choice']['function']['name']
            arguments={'run_ids':list(self.session.state['runs'])} if name in ('read_evidence','compare_runs') else self.to_compact(self._prose_answer)
            if name == 'present_report' and 'question' in payload['tools'][-1]['function']['parameters']['properties']:
                arguments['question'] = self._prose_index.get(arguments.pop('question_ref'), '')
                for option in arguments['options']: option['description'] = self._prose_index[option.pop('description_ref')]
            result={'role':'assistant','content':None,'tool_calls':[{'id':f'tool_call_{index}','type':'function','function':{'name':name,'arguments':json.dumps(arguments,ensure_ascii=False)}}]};finish='tool_calls'
        write_json(p/f'call-{index:02d}.request.json',payload)
        write_json(p/f'call-{index:02d}.response.json',{'model':'mock','choices':[{'message':result,'finish_reason':finish}]})
        write_json(p/f'call-{index:02d}.meta.json',{'status':'completed','provider':'mock','model':'mock','elapsed_s':.01})
        return result,finish

    def to_compact(self,a):
        def ref(text):
            if not text:return ''
            return next(k for k,v in self._prose_index.items() if v==text)
        flat=self.to_wire(a)
        compact={'request_sha256':a['request_sha256'],'decision':a['assessment']['decision'],
                 'summary_ref':ref(a['assessment']['summary']),'next_requirement_ref':ref(a['assessment']['next_requirement']),
                 'observations':flat['observations'],'hypotheses':[],'blocks':[],
                 'question_ref':ref(a['question']['title']) if a['question'] else '', 'options':[]}
        for h in flat['hypotheses']:
            compact['hypotheses'].append({k:h[k] for k in ('id','status','evidence')}|{k+'_ref':ref(h[k]) for k in ('claim','scope','reason','criterion','test_basis')})
        included=False
        for b in flat['blocks']:
            if b['type']=='markdown' and included:continue
            compact['blocks'].append({k:b[k] for k in ('evidence','run_ids','view')}|{'type':'analysis' if b['type']=='markdown' else b['type'],'title_ref':ref(b['title']),'text_ref':ref(b['text']) if b['type']=='callout' else ''}|({'tone':b['tone']} if 'tone' in b else {}))
            included|=b['type']=='markdown'
        for o in flat['options']:
            compact['options'].append({k:v for k,v in o.items() if k not in ('label','description','message')}|{'label':o['label'],'description_ref':ref(o['description']),'message_ref':'' if o['tool'] in ('conclude','deepen') else ref(o['message'])})
        return compact

    def to_wire(self,a):
        v=a['assessment'];wire={k:v[k] for k in ('goal','decision','summary','next_requirement')}
        wire.update(request_sha256=a['request_sha256'],observations=[c['id'] for c in v['claims'] if c['kind']=='observation'],
                    hypotheses=[{k:c.get(k,'') for k in ('id','claim','status','scope','reason','evidence','criterion','test_basis')} for c in v['claims'] if c['kind']=='hypothesis'],blocks=[],question=a['question']['title'] if a['question'] else '',options=[])
        for b in a['blocks']:
            block={'type':b['type'],'title':b['title'],'text':'','evidence':[],'run_ids':[],'view':'full','tone':'info'}|b
            if b['type']=='callout' and 'tone' not in b:block.pop('tone')
            wire['blocks'].append(block)
        for o in (a.get('question') or {}).get('options',[]):
            args=o['arguments'];item={k:o[k] for k in ('id','label','description','recommended','tool')}
            item.update(experiment_key=args['operation']+':'+args['reference_run'] if o['tool']=='run_experiment' else 'none',event_at_s=args.get('event_at_s',0),message=args.get('message',''))
            item.update({k:v for k,v in args.items() if k not in ('operation','reference_run','event_at_s','message')});wire['options'].append(item)
        return wire

    def completed_turn(self):
        with patch.object(agent,'api_call',side_effect=self.fake_api) as call:
            self.session.respond('分析与建议',new_experiment=True)
            self.assertEqual(call.call_count,4 if len(self.session.state['runs'])>1 else 3)
        return self.session.state['turns'][-1]

    def test_parameterized_delay_preserves_plant_and_performance_thresholds(self):
        c,anchor,diff=tools.build_config({'operation':'delay_event','reference_run':'R001','event_at_s':1.3},self.session.state['runs'],self.root)
        self.assertEqual(anchor,1.3);self.assertEqual(c['capture']['duration_s'],2.3)
        self.assertEqual(c['acceptance']['min_samples'],23000)
        self.assertEqual(c['acceptance']['max_deviation_relative'],.1)
        self.assertEqual(c['parameters'],load_config(PROJECT/'configs/boost_vin_drop.json')['parameters'])
        self.assertEqual({x['field'] for x in diff},{'/events','/capture/duration_s','/acceptance/min_samples'})

    def test_experiment_contract_rejects_arbitrary_keys_nonfinite_times_and_unknown_runs(self):
        for a in ({'operation':'shell','reference_run':'R001'},{'operation':'repeat','reference_run':'../outside'},
                  {'operation':'delay_event','reference_run':'R001','event_at_s':float('nan')},
                  {'operation':'delay_event','reference_run':'R001','event_at_s':.50001},
                  {'operation':'delay_event','reference_run':'R001','event_at_s':2.6},
                  {'operation':'repeat','reference_run':'R001','acceptance':{'max_deviation_relative':.5}}):
            with self.subTest(arguments=a),self.assertRaises(ValueError):tools.build_config(a,self.session.state['runs'],self.root)

    def test_baseline_uses_its_declared_reference_not_a_fabricated_event(self):
        e=self.add_run('R002',event=1.0,baseline=True)
        ev=tools.evidence_for(e,self.root)
        self.assertEqual(ev['anchor_kind'],'baseline_reference_no_event')
        self.assertAlmostEqual(ev['anchor_s'],1.0000005)
        self.assertEqual(ev['aligned_response']['sample_count'],9000)
        self.assertAlmostEqual(ev['pre_event_trend']['slope_v_per_s'],0)
        self.assertFalse(ev['metrics']['events'])

    def test_real_tool_message_roundtrip_and_model_authored_layout(self):
        turn=self.completed_turn();p=self.root/turn['path']
        messages=agent.read(p/'call-02.request.json')['messages']
        self.assertEqual(messages[-2]['role'],'tool');self.assertEqual(messages[-2]['tool_call_id'],'tool_call_1')
        model_message=self.session.state['messages'][-1]
        self.assertLess(model_message['html'].index('模型决定先看指标'),model_message['html'].index('模型决定后解释'))
        self.assertEqual(agent.verify_session(self.root)['record_status'],'passed')

    def test_model_comparison_tool_reads_actual_common_windows(self):
        self.add_run('R002',event=1.0)
        turn=self.completed_turn();p=self.root/turn['path']
        calls=agent.read(p/'tool_calls.json')
        self.assertEqual(calls[0]['name'],'compare_runs')
        self.assertTrue(all(x['sample_count']==9000 for x in calls[0]['output']['rows']))

    def test_suggestion_does_not_execute_and_confirmation_requires_unchanged_config(self):
        turn=self.completed_turn()
        with patch('typhoon_lab.runtime.execute_case') as execute:
            result=self.session.launch('choose',{'turn_id':turn['id'],'option_id':'delay13'})
            execute.assert_not_called()
            plan=result['pending'];self.assertEqual(plan['anchor_s'],1.3)
            with self.assertRaises(ValueError):self.session.launch('confirm',{'plan_id':plan['id'],'token':plan['confirmation_token'],'approved':False,'operator':'human'})
            path=self.root/'plans'/plan['id']/'config.json';c=agent.read(path);c['acceptance']['max_deviation_relative']=.3;write_json(path,c)
            with self.assertRaises(ValueError):self.session.launch('confirm',{'plan_id':plan['id'],'token':plan['confirmation_token'],'approved':True,'operator':'human'})
            execute.assert_not_called()

    def test_confirmed_dispatch_is_once_and_binds_to_model_option(self):
        turn=self.completed_turn();plan=self.session.launch('choose',{'turn_id':turn['id'],'option_id':'delay13'})['pending']
        data={'plan_id':plan['id'],'token':plan['confirmation_token'],'approved':True,'operator':'test human'}
        with patch.object(agent.threading,'Thread') as thread:
            self.session.launch('confirm',data)
            self.assertTrue(self.session.state['busy']);self.assertTrue((self.root/'plans'/plan['id']/'confirmation.json').is_file())
            with self.assertRaises(ValueError):self.session.launch('confirm',data)
            self.assertEqual(thread.call_count,1)

    def test_old_question_cannot_be_confirmed_after_a_new_turn(self):
        turn=self.completed_turn();self.session.state['active_turn']='T999';self.session.persist('fixture_new_turn',{})
        with self.assertRaises(ValueError):self.session.launch('choose',{'turn_id':turn['id'],'option_id':'delay13'})

    def test_failed_or_unknown_tool_never_becomes_an_experiment(self):
        def invalid(p,index,payload,service):
            write_json(p/'call-01.meta.json',{'status':'completed'})
            return {'content':None,'tool_calls':[{'id':'bad','function':{'name':'run_shell','arguments':'{}'}}]},'tool_calls'
        with patch.object(agent,'api_call',side_effect=invalid),patch('typhoon_lab.runtime.execute_case') as execute:
            with self.assertRaises(ValueError):self.session.respond('分析',new_experiment=True)
            execute.assert_not_called()
        self.assertFalse(any(x['role']=='assistant' for x in self.session.state['messages']))

    def test_layout_rejects_unknown_blocks_refs_runs_and_script_tools(self):
        ev={'R001':tools.evidence_for(self.session.state['runs']['R001'],self.root)}
        for mutate in (lambda a:a['blocks'][0].update(type='javascript'),
                       lambda a:a['blocks'][0].update(run_ids=['not_here']),
                       lambda a:a['blocks'][1].update(evidence=['R001.nonexistent']),
                       lambda a:a['question']['options'][0].update(tool='shell')):
            a=self.answer('h');mutate(a)
            with self.assertRaises(ValueError):tools.validate_answer(a,'h',ev,self.session.state['runs'],self.root)

    def test_markdown_and_model_text_cannot_inject_html(self):
        text=markdown('<script>alert(1)</script>\n[click](javascript:alert)\n**strong**')
        self.assertNotIn('<script>',text);self.assertNotIn('href="javascript:',text);self.assertIn('<strong>strong</strong>',text)

    def test_export_and_event_journal_detect_tampering(self):
        self.completed_turn();self.session.export()
        report=(self.root/'report.html').read_text(encoding='utf-8')
        self.assertIn('模型决定先看指标',report);self.assertIn('延后至1.3秒',report)
        self.assertEqual(agent.verify_session(self.root)['record_status'],'passed')
        state=agent.read(self.root/'session.json');state['message']='tampered';write_json(self.root/'session.json',state)
        self.assertEqual(agent.verify_session(self.root)['record_status'],'failed')

    def test_raw_waveform_tampering_is_detected_without_replaying_model(self):
        self.completed_turn()
        with (self.root/'runs/R001/waveforms.csv').open('a',encoding='utf-8') as f:f.write('broken\n')
        with patch.object(agent,'api_call') as call:
            self.assertEqual(agent.verify_session(self.root)['record_status'],'failed');call.assert_not_called()

    def test_common_verify_dispatches_to_agent_without_model_replay(self):
        from typhoon_lab.records import verify_run
        self.completed_turn()
        with patch.object(agent,'api_call') as call:
            self.assertEqual(verify_run(self.root,write=False)['record_status'],'passed');call.assert_not_called()

    def test_tool_output_is_recomputed_even_if_artifact_hashes_are_rebuilt(self):
        turn=self.completed_turn();p=self.root/turn['path'];calls=agent.read(p/'tool_calls.json')
        calls[0]['output']['R001']['record_status']='fabricated'
        write_json(p/'tool_calls.json',calls);finalize(p,agent.read(p/'manifest.json'))
        result=agent.verify_session(self.root)
        self.assertEqual(result['record_status'],'failed')
        self.assertTrue(any('recomputed output differs' in x for x in result['problems']))

    def test_optional_callout_style_falls_back_safely_without_changing_answer(self):
        ev={'R001':tools.evidence_for(self.session.state['runs']['R001'],self.root)}
        for hint in ({},{'tone':None},{'tone':''},{'tone':'danger'},{'tone':{'style':'warning'}},
                     {'tone':'warning" onclick="alert(1)'},{'tone':'warning'}):
            with self.subTest(hint=hint):
                a=self.answer('h');a['blocks'].append({'type':'callout','title':'证据局限','text':'需要进一步验证。','evidence':['R001.metrics'],**hint})
                original=deepcopy(a);tools.validate_answer(a,'h',ev,self.session.state['runs'],self.root)
                output=render_answer(a,ev,{},str)
                expected='warning' if hint.get('tone')=='warning' else 'info'
                self.assertIn('<aside class="callout '+expected+'">',output)
                self.assertNotIn('onclick=',output);self.assertEqual(a,original)

    def test_missing_callout_style_survives_full_turn_and_raw_response_verification(self):
        original=self.answer
        def missing(request_hash):
            a=original(request_hash);a['blocks'].append({'type':'callout','title':'证据局限','text':'需要验证。','evidence':['R001.metrics']});return a
        with patch.object(self,'answer',side_effect=missing),patch('typhoon_lab.runtime.execute_case') as execute:
            turn=self.completed_turn();execute.assert_not_called()
        self.assertEqual(turn['status'],'passed')
        p=self.root/turn['path'];raw=agent.response_answer(agent.read(p/f"call-{agent.read(p/'manifest.json')['final_call_index']:02d}.response.json"),agent.read(p/'manifest.json')['report_call_id'])
        self.assertNotIn('tone',raw['blocks'][-1]);self.assertEqual(raw,agent.read(p/'wire_answer.json'))
        self.assertEqual(agent.verify_session(self.root)['record_status'],'passed')

    def test_style_fallback_does_not_accept_invalid_evidence_or_experiment_arguments(self):
        ev={'R001':tools.evidence_for(self.session.state['runs']['R001'],self.root)}
        for mutate in (lambda a:a['blocks'][-1].update(evidence=['R001.fabricated']),
                       lambda a:a['question']['options'][0]['arguments'].update(max_deviation_relative=.99),
                       lambda a:a['question']['options'][0].update(tool='shell')):
            a=self.answer('h');a['blocks'].append({'type':'callout','title':'证据局限','text':'需要验证。','evidence':['R001.metrics']});mutate(a)
            with self.assertRaises(ValueError):tools.validate_answer(a,'h',ev,self.session.state['runs'],self.root)

    def test_api_timeout_is_recorded_without_credential_in_artifacts(self):
        p=self.root/'api';p.mkdir()
        service={'model':'mock','provider':'mock','base_url':'https://example.invalid','timeout_s':1,'max_tokens':1000}
        class Opener:
            def open(self,*args,**kwargs):raise TimeoutError('secret-key-value')
        with patch.object(agent,'load_service',return_value=(service,'secret-key-value')),patch.object(agent.urllib.request,'build_opener',return_value=Opener()):
            with self.assertRaises(RuntimeError):agent.api_call(p,1,{'messages':[]},'unused')
        for f in p.iterdir():self.assertNotIn('secret-key-value',f.read_text(encoding='utf-8'))

    def test_strict_schema_binds_evidence_and_excludes_delay_of_baseline(self):
        from typhoon_lab.boost_agent_schema import strict_tools
        self.add_run('R002',event=1.0,baseline=True)
        ev={k:tools.evidence_for(v,self.root) for k,v in self.session.state['runs'].items()}
        definitions=strict_tools('h',ev,self.session.state['runs'],self.root,6)
        def walk(value):
            if isinstance(value,dict):
                if value.get('type')=='object':
                    self.assertFalse(value['additionalProperties']);self.assertEqual(set(value['required']),set(value['properties']))
                for v in value.values():yield from walk(v)
                yield value
            elif isinstance(value,list):
                for v in value:yield from walk(v)
        nodes=list(walk(definitions));self.assertTrue(all(d['function']['strict'] for d in definitions))
        delayed=[n for n in nodes if n.get('properties',{}).get('operation',{}).get('enum')==['delay_event']]
        self.assertEqual(len(delayed),1);self.assertEqual(delayed[0]['properties']['reference_run']['enum'],['R001'])
        self.assertEqual(definitions[0]['function']['parameters']['properties']['run_ids']['enum'],[['R001','R002']])
        no_runs_left=strict_tools('h',ev,self.session.state['runs'],self.root,0)[-1]
        self.assertNotIn('run_experiment',json.dumps(no_runs_left))

    def test_malformed_strict_response_stops_without_automatic_repair_or_experiment(self):
        malformed='{"question":{"options":[{"id":"a"},"options_placeholder":null]}}'
        def bad(p,index,payload,service):
            m,f=self.fake_api(p,index,payload,service)
            if payload['tool_choice']=='auto' or (isinstance(payload['tool_choice'],dict) and payload['tool_choice']['function']['name']=='present_report'):
                m['tool_calls'][0]['function']['arguments']=malformed
                raw=agent.read(p/f'call-{index:02d}.response.json');raw['choices'][0]['message']=m;write_json(p/f'call-{index:02d}.response.json',raw)
            return m,f
        with patch.object(agent,'api_call',side_effect=bad) as api,patch('typhoon_lab.runtime.execute_case') as execute:
            with self.assertRaisesRegex(ValueError,'JSON解析失败'):self.session.respond('分析',new_experiment=True)
            self.assertEqual(api.call_count,3);execute.assert_not_called()
        p=self.root/'turns/T001';self.assertEqual(agent.read(p/'format_error.json')['type'],'JSONDecodeError')
        self.assertFalse((p/'answer.json').exists());self.assertNotIn('format_repair_count',agent.read(p/'manifest.json'))

    def test_strict_report_still_rejects_experiment_parameter_changes(self):
        original=self.answer
        def unsafe(h):
            a=original(h);a['question']['options'][0]['arguments']['max_deviation_relative']=.99;return a
        with patch.object(self,'answer',side_effect=unsafe),patch.object(agent,'api_call',side_effect=self.fake_api) as api,patch('typhoon_lab.runtime.execute_case') as execute:
            with self.assertRaisesRegex(ValueError,'结构化参数校验失败'):self.session.respond('分析',new_experiment=True)
            self.assertEqual(api.call_count,3);execute.assert_not_called()

    def test_retry_compares_completed_run_that_has_no_successful_report(self):
        self.completed_turn();self.add_run('R002',event=1.0,baseline=True)
        with patch.object(agent,'api_call',side_effect=self.fake_api) as api,patch('typhoon_lab.runtime.execute_case') as execute:
            self.session.respond('重新分析已有证据',new_experiment=False);execute.assert_not_called()
        self.assertEqual(api.call_args_list[0].args[2]['tool_choice']['function']['name'],'compare_runs')
        self.assertEqual(api.call_count,4);self.assertEqual(agent.verify_session(self.root)['record_status'],'passed')

    def test_strict_request_schema_tampering_is_detected(self):
        turn=self.completed_turn();p=self.root/turn['path'];path=p/f"call-{agent.read(p/'manifest.json')['final_call_index']:02d}.request.json";r=agent.read(path)
        r['tools'][0]['function']['strict']=False;write_json(path,r);finalize(p,agent.read(p/'manifest.json'))
        result=agent.verify_session(self.root);self.assertEqual(result['record_status'],'failed')
        self.assertIn('report was not generated through strict tool schema',result['problems'])

    def test_legacy_content_report_remains_verifiable_without_api_replay(self):
        turn=self.completed_turn();p=self.root/turn['path'];r=agent.read(p/f"call-{agent.read(p/'manifest.json')['final_call_index']:02d}.response.json");a=agent.read(p/'answer.json')
        a.pop('assessment');a['cause_status']='undetermined';write_json(p/'answer.json',a)
        r['choices'][0]={'message':{'role':'assistant','content':json.dumps(a)},'finish_reason':'stop'};write_json(p/f"call-{agent.read(p/'manifest.json')['final_call_index']:02d}.response.json",r)
        m=agent.read(p/'manifest.json');m.pop('output_contract');m.pop('report_call_id');finalize(p,m)
        with patch.object(agent,'api_call') as api:self.assertEqual(agent.verify_session(self.root)['record_status'],'passed');api.assert_not_called()

    def test_claims_can_establish_observation_and_weaken_hypothesis_in_same_report(self):
        a=self.answer('h');a['assessment']['claims'].append({'id':'startup','kind':'hypothesis','status':'weakened','claim':'启动残余足以解释下冲','scope':'当前工况','reason':'该解释的支持减弱。','evidence':['R001.metrics']})
        ev={'R001':tools.evidence_for(self.session.state['runs']['R001'],self.root)}
        tools.validate_answer(a,'h',ev,self.session.state['runs'],self.root)
        self.assertNotIn('cause_status',a)
        output=render_answer(a,ev,{},str);self.assertIn('数据中可以确认',output);self.assertIn('这一解释的支持减弱了',output);self.assertIn('<li',output)

    def test_claims_require_scope_and_actual_evidence(self):
        ev={'R001':tools.evidence_for(self.session.state['runs']['R001'],self.root)}
        for change in ({'scope':''},{'evidence':['R999.metrics']},{'reason':''}):
            a=self.answer('h');a['assessment']['claims'][0].update(change)
            with self.assertRaises(ValueError):tools.validate_answer(a,'h',ev,self.session.state['runs'],self.root)

    def test_new_schema_exposes_conclude_and_deepen_and_constrain_repeat_recommendation(self):
        from typhoon_lab.boost_agent_investigation import context_for
        ev={'R001':tools.evidence_for(self.session.state['runs']['R001'],self.root)};ctx=context_for(ev,self.session.state['runs'],self.root)
        schema=agent.strict_tools('h',ev,self.session.state['runs'],self.root,7,ctx)[-1]['function']['parameters']
        self.assertNotIn('cause_status',schema['properties']);self.assertIn('decision',schema['properties'])
        self.assertTrue({'conclude','deepen'}<=set(schema['properties']['options']['items']['properties']['tool']['enum']))
        wire=self.to_wire(self.answer('h'));wire['options'][0].update(experiment_key='repeat:R001',event_at_s=0)
        from typhoon_lab.boost_agent_wire import project_answer
        with self.assertRaisesRegex(ValueError,'一致性'):project_answer(wire,ctx)

    def _choice_turn(self):
        self.add_run('R002',event=1.0)
        original=self.answer
        def choices(h):
            a=original(h);a['assessment']['decision']='ready_to_conclude';a['question']['options']=[
                {'id':action,'tool':action,'label':action,'description':'用户决定是否继续。','recommended':action=='conclude','arguments':{'message':'形成阶段结论。' if action=='conclude' else '继续定位具体机理。'}} for action in ('conclude','deepen')];return a
        with patch.object(self,'answer',side_effect=choices):return self.completed_turn()

    def test_conclude_choice_only_dispatches_analysis(self):
        turn=self._choice_turn()
        with patch.object(agent.threading,'Thread') as thread,patch('typhoon_lab.runtime.execute_case') as execute:
            self.session.launch('choose',{'turn_id':turn['id'],'option_id':'conclude'});execute.assert_not_called()
        self.assertEqual(thread.call_args.kwargs['args'][0],'analysis');self.assertEqual(thread.call_args.kwargs['args'][2],{'intent':'conclude'})
        self.assertIsNone(self.session.state['pending'])

    def test_deepen_choice_changes_goal_without_dispatching_experiment(self):
        turn=self._choice_turn()
        with patch.object(agent.threading,'Thread') as thread,patch('typhoon_lab.runtime.execute_case') as execute:
            self.session.launch('choose',{'turn_id':turn['id'],'option_id':'deepen'});execute.assert_not_called()
        self.assertEqual(thread.call_args.kwargs['args'][0],'analysis');self.assertEqual(self.session.state['investigation_goal'],'identify_mechanism')
        self.assertIsNone(self.session.state['pending'])

    def test_conclusion_has_no_new_question_and_retains_unresolved_claim(self):
        original=self.answer
        def closing(h):
            a=original(h);a['assessment']['decision']='complete';a['assessment']['claims'].append({'id':'mechanism','kind':'hypothesis','status':'unresolved','claim':'具体下冲机理','scope':'本模型','reason':'未采集内部状态。','evidence':['R001.config']});a['question']=None;return a
        with patch.object(self,'answer',side_effect=closing),patch.object(agent,'api_call',side_effect=self.fake_api),patch('typhoon_lab.runtime.execute_case') as execute:
            self.session.respond('请收尾',intent='conclude');execute.assert_not_called()
        self.assertIsNone(self.session.state['active_turn']);self.assertEqual(self.session.state['investigation_phase'],'complete')
        self.assertEqual(agent.verify_session(self.root)['record_status'],'passed')

    def test_signal_context_is_recomputed_after_hashes_are_rebuilt(self):
        turn=self.completed_turn();p=self.root/turn['path'];ctx=agent.read(p/'investigation_context.json')
        ctx['signal_stats']['R001']['whole_capture_current_peak']['first_simulation_time_s']+=.1
        write_json(p/'investigation_context.json',ctx);finalize(p,agent.read(p/'manifest.json'))
        result=agent.verify_session(self.root);self.assertEqual(result['record_status'],'failed')
        self.assertTrue(any('recomputed investigation context differs' in x for x in result['problems']))

    def test_additional_advertised_read_only_comparison_is_allowed_before_report(self):
        self.add_run('R002',event=1.0,baseline=True);self.completed_turn()
        def extra(p,index,payload,service):
            m,f=self.fake_api(p,index,payload,service)
            if index==3:
                m['tool_calls'][0]['function']={'name':'compare_runs','arguments':json.dumps({'run_ids':['R001','R002']})}
                raw=agent.read(p/f'call-{index:02d}.response.json');raw['choices'][0]['message']=m;write_json(p/f'call-{index:02d}.response.json',raw)
            return m,f
        with patch.object(agent,'api_call',side_effect=extra) as api,patch('typhoon_lab.runtime.execute_case') as execute:
            self.session.respond('复核已有证据');execute.assert_not_called()
        self.assertEqual(api.call_count,4);self.assertEqual(agent.verify_session(self.root)['record_status'],'passed')

    def test_conclusion_intent_rejects_a_new_question(self):
        from typhoon_lab.boost_agent_investigation import context_for
        ev={'R001':tools.evidence_for(self.session.state['runs']['R001'],self.root)};ctx=context_for(ev,self.session.state['runs'],self.root,intent='conclude')
        a=self.answer('h');a['assessment']['decision']='complete'
        with self.assertRaisesRegex(ValueError,'收尾'):tools.validate_answer(a,'h',ev,self.session.state['runs'],self.root,ctx)

    def test_model_history_keeps_semantics_without_repeating_ui_json_protocol(self):
        self.completed_turn()
        from typhoon_lab.boost_agent_investigation import history_for
        history=history_for(self.session.state['messages'])
        self.assertEqual(history[-1]['role'],'assistant');self.assertIn('已有记录可用于分析',history[-1]['text']);self.assertIn('延后至1.3秒',history[-1]['text'])
        self.assertNotIn('answer',history[-1]);self.assertNotIn('blocks',history[-1])

    def test_quoted_narrative_never_enters_generated_json_parameters(self):
        original=self.answer
        quoted='这削弱了"跌落瞬间出现大电流尖峰"这一说法。路径 C:\\temp\\波形 可以正常出现在正文。'
        def prose(h):
            a=original(h);a['blocks'][1]['text']=quoted
            a['assessment']['claims'].append({'id':'quoted_reason','kind':'hypothesis','status':'weakened',
                'claim':'电流峰值解释','scope':'当前保存的采样窗口','reason':quoted,'evidence':['R001.metrics']})
            return a
        with patch.object(self,'answer',side_effect=prose),patch('typhoon_lab.runtime.execute_case') as execute:
            turn=self.completed_turn();execute.assert_not_called()
        p=self.root/turn['path'];m=agent.read(p/'manifest.json')
        self.assertIn(quoted,(p/'narrative.md').read_text(encoding='utf-8'))
        self.assertNotIn('跌落瞬间',(p/'wire_answer.json').read_text(encoding='utf-8'))
        self.assertIn('这削弱了&quot;跌落瞬间',self.session.state['messages'][-1]['html'])
        self.assertEqual(m['output_contract'],'strict_tool_v6')
        self.assertEqual(agent.verify_session(self.root)['record_status'],'passed')

    def test_invalid_controls_preserve_read_only_narrative_without_options(self):
        def malformed(p,index,payload,service):
            message,finish=self.fake_api(p,index,payload,service)
            if payload['tool_choice']=='auto':
                message['tool_calls'][0]['function']['arguments']='{"x":"这削弱了"尖峰""}'
                raw=agent.read(p/f'call-{index:02d}.response.json');raw['choices'][0]['message']=message;write_json(p/f'call-{index:02d}.response.json',raw)
            return message,finish
        with patch.object(agent,'api_call',side_effect=malformed) as api,patch('typhoon_lab.runtime.execute_case') as execute:
            with self.assertRaisesRegex(ValueError,'JSON解析失败'):self.session.respond('分析')
            self.assertEqual(api.call_count,3);execute.assert_not_called()
        draft=self.session.state['messages'][-1]
        self.assertEqual(draft['role'],'draft');self.assertNotIn('answer',draft)
        self.assertIsNone(self.session.state['active_turn']);self.assertIsNone(self.session.state['pending'])
        self.session.export();self.assertNotIn('<section class="question"',(self.root/'report.html').read_text(encoding='utf-8'))
        self.assertEqual(agent.read(self.root/'turns/T001/format_error.json')['category'],'json_syntax')
        self.assertEqual(agent.verify_session(self.root)['record_status'],'passed')

    def test_narrative_reference_tampering_is_detected_after_rehashing(self):
        turn=self.completed_turn();p=self.root/turn['path'];index=agent.read(p/'narrative_index.json')
        index['P001']='篡改段落';write_json(p/'narrative_index.json',index);finalize(p,agent.read(p/'manifest.json'))
        self.assertEqual(agent.verify_session(self.root)['record_status'],'failed')

    def test_controls_request_must_bind_to_the_saved_narrative(self):
        turn=self.completed_turn();p=self.root/turn['path'];m=agent.read(p/'manifest.json')
        path=p/f"call-{m['final_call_index']:02d}.request.json";request=agent.read(path)
        binding=json.loads(request['messages'][-1]['content']);binding['narrative_sha256']='0'*64
        request['messages'][-1]['content']=json.dumps(binding);write_json(path,request);finalize(p,m)
        self.assertIn('report controls were not bound to the narrative',agent.verify_session(self.root)['problems'])

    def test_unknown_prose_references_are_business_errors_not_json_errors(self):
        original=self.to_compact
        def bad(a):
            wire=original(a);wire['summary_ref']='P999';return wire
        with patch.object(self,'to_compact',side_effect=bad),patch.object(agent,'api_call',side_effect=self.fake_api) as api:
            with self.assertRaisesRegex(ValueError,'结构化参数校验失败.*正文段落'):self.session.respond('分析')
        self.assertEqual(api.call_count,3)
        self.assertEqual(agent.read(self.root/'turns/T001/format_error.json')['category'],'report_validation')

    def test_truncated_narrative_stops_before_control_generation(self):
        def truncated(p,index,payload,service):
            message,finish=self.fake_api(p,index,payload,service)
            if payload['tool_choice']=='none':
                raw=agent.read(p/f'call-{index:02d}.response.json');raw['choices'][0]['finish_reason']='length';write_json(p/f'call-{index:02d}.response.json',raw)
                return message,'length'
            return message,finish
        with patch.object(agent,'api_call',side_effect=truncated) as api:
            with self.assertRaisesRegex(ValueError,'正文生成未完成'):self.session.respond('分析')
        self.assertEqual(api.call_count,2)
        self.assertEqual(agent.read(self.root/'turns/T001/format_error.json')['category'],'narrative_output')
        self.assertFalse(any(m['role']=='draft' for m in self.session.state['messages']))

    def test_goal_choices_use_declared_commands_with_empty_message_refs(self):
        from typhoon_lab.boost_agent_prose import GOAL_MESSAGES
        with patch('typhoon_lab.runtime.execute_case') as execute:
            turn=self._choice_turn();execute.assert_not_called()
        p=self.root/turn['path'];wire=agent.read(p/'wire_answer.json');answer=agent.read(p/'answer.json')
        self.assertTrue(all(o['message_ref']=='' for o in wire['options']))
        self.assertEqual({o['tool']:o['arguments']['message'] for o in answer['question']['options']},GOAL_MESSAGES)

    def test_generation_schema_and_projection_agree_on_option_requirements(self):
        import jsonschema
        turn=self.completed_turn();p=self.root/turn['path'];m=agent.read(p/'manifest.json')
        schema=agent.read(p/f"call-{m['final_call_index']:02d}.request.json")['tools'][-1]['function']['parameters']
        wire=agent.read(p/'wire_answer.json');jsonschema.validate(wire,schema)
        ctx=agent.read(p/'investigation_context.json');index=agent.read(p/'narrative_index.json');body=(p/'narrative.md').read_text(encoding='utf-8')
        bad=deepcopy(wire);bad['options'][1]['message_ref']=''
        with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(bad,schema)
        with self.assertRaisesRegex(ValueError,'讨论选项需引用非空'):agent.project_compact(bad,ctx,index,body,3)
        for label in ('两行\n标题','英文"引号','反斜杠\\标题'):
            bad=deepcopy(wire);bad['options'][0]['label']=label
            with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(bad,schema)
            with self.assertRaisesRegex(ValueError,'选项标题'):agent.project_compact(bad,ctx,index,body,3)

    def test_option_titles_are_independent_of_combined_suggestion_paragraph(self):
        import jsonschema
        turn=self.completed_turn();p=self.root/turn['path'];wire=agent.read(p/'wire_answer.json')
        wire['question_ref']=wire.pop('question')
        for o in wire['options']:o['description_ref']=o.pop('description')
        body='其一“延后至1.3秒”用于验证趋势，其二“先讨论”用于解释已有证据。'
        index={'P001':body};wire['summary_ref']='P001';wire['next_requirement_ref']='P001';wire['question_ref']='P001'
        for b in wire['blocks']:b['title_ref']='P001'
        for o in wire['options']:
            o['description_ref']='P001';o['message_ref']='P001' if o['tool']=='discuss' else ''
        ctx=agent.read(p/'investigation_context.json');ev=agent.read(p/'evidence.json');h=wire['request_sha256']
        schema=agent.strict_tools(h,ev,self.session.state['runs'],self.root,7,ctx,index,2)[-1]['function']['parameters']
        jsonschema.validate(wire,schema)
        answer=tools.validate_answer(agent.project_compact(wire,ctx,index,body,2),h,ev,self.session.state['runs'],self.root,ctx)
        self.assertEqual([o['label'] for o in answer['question']['options']],['延后至1.3秒','先讨论'])

    def test_legacy_v4_schema_and_projection_remain_available(self):
        import jsonschema
        turn=self._choice_turn();p=self.root/turn['path'];wire=agent.read(p/'wire_answer.json')
        ctx=agent.read(p/'investigation_context.json');ev=agent.read(p/'evidence.json');index=agent.read(p/'narrative_index.json');body=(p/'narrative.md').read_text(encoding='utf-8');h=wire['request_sha256']
        question=wire.pop('question');wire['question_ref']=next(k for k,v in index.items() if v==question)
        for o in wire['options']:
            description=o.pop('description');o['description_ref']=next(k for k,v in index.items() if v==description)
            label=o.pop('label');o['label_ref']=next(k for k,v in index.items() if v==label)
        schema=agent.strict_tools(h,ev,self.session.state['runs'],self.root,7,ctx,index)[-1]['function']['parameters']
        jsonschema.validate(wire,schema)
        with self.assertRaisesRegex(ValueError,'追问选项无效'):
            tools.validate_answer(agent.project_compact(wire,ctx,index,body),h,ev,self.session.state['runs'],self.root,ctx)
        for o in wire['options']:o['message_ref']=next(iter(index))
        tools.validate_answer(agent.project_compact(wire,ctx,index,body),h,ev,self.session.state['runs'],self.root,ctx)

    def test_first_run_retry_and_identical_repeat_do_not_open_conclusion_branch(self):
        import jsonschema
        from typhoon_lab.boost_agent_investigation import context_for
        for repeat in (False, True):
            if repeat:self.add_run('R002')
            ev={k:tools.evidence_for(v,self.root) for k,v in self.session.state['runs'].items()}
            ctx=context_for(ev,self.session.state['runs'],self.root)
            schema=agent.strict_tools('h',ev,self.session.state['runs'],self.root,6,ctx,{'P001':'需要对照。'},3)[-1]['function']['parameters']
            self.assertNotIn('ready_to_conclude',schema['properties']['decision']['enum'])
            self.assertNotIn('complete',schema['properties']['decision']['enum'])
            actions={t for v in schema['properties']['options']['items']['anyOf'] for t in v['properties']['tool']['enum']}
            self.assertEqual(actions,{'discuss','run_experiment'})
            wire={'request_sha256':'h','decision':'ready_to_conclude','summary_ref':'P001','next_requirement_ref':'',
                  'observations':['disturbance_peaks'],'hypotheses':[], 'blocks':[], 'question':'下一步？','options':[]}
            with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(wire,schema)
            with self.assertRaisesRegex(ValueError,'尚无实际时刻对照'):agent.project_compact(wire,ctx,{'P001':'需要对照。'},'需要对照。',3)
            wire['decision']='continue'
            for action in ('conclude','deepen'):
                wire['options']=[{'tool':action,'description':'总结或定位'}]
                with self.assertRaisesRegex(ValueError,'尚无实际时刻对照'):agent.project_compact(wire,ctx,{'P001':'需要对照。'},'需要对照。',3)

    def test_contrast_enables_branch_without_forcing_closure(self):
        from typhoon_lab.boost_agent_investigation import context_for
        self.add_run('R002',event=1)
        ev={k:tools.evidence_for(v,self.root) for k,v in self.session.state['runs'].items()}
        ctx=context_for(ev,self.session.state['runs'],self.root)
        schema=agent.strict_tools('h',ev,self.session.state['runs'],self.root,6,ctx,{'P001':'对照结果。'},3)[-1]['function']['parameters']
        self.assertTrue({'continue','ready_to_conclude'}<=set(schema['properties']['decision']['enum']))
        actions={t for v in schema['properties']['options']['items']['anyOf'] for t in v['properties']['tool']['enum']}
        self.assertTrue({'conclude','deepen'}<=actions)

    def test_shared_prose_is_rendered_once_with_details_collapsed(self):
        a=self.answer('h');body='这一整段同时被引用为表述、范围、依据和验证说明。'
        a['blocks']=[{'type':'markdown','title':body,'text':body,'evidence':['R001.metrics']},
                     {'type':'callout','title':'说明','text':body,'evidence':['R001.metrics']}]
        a['assessment'].update(summary=body,next_requirement=body)
        a['assessment']['claims']=[{'id':'startup','kind':'hypothesis','status':'unresolved',
            **{k:body for k in ('claim','scope','reason','criterion','test_basis')},'evidence':['R001.metrics']}]
        original=deepcopy(a);output=render_answer(a,{}, {},str)
        self.assertEqual(output.count(body),1);self.assertEqual(a,original)
        self.assertIn('<details class="evidence-details">',output);self.assertNotIn(' open',output)
        self.assertNotIn('观察 ·',output);self.assertNotIn('假说 ·',output)

    def test_short_question_and_option_descriptions_are_checked(self):
        import jsonschema
        turn=self.completed_turn();p=self.root/turn['path'];m=agent.read(p/'manifest.json')
        wire=agent.read(p/'wire_answer.json');ctx=agent.read(p/'investigation_context.json')
        index=agent.read(p/'narrative_index.json');body=(p/'narrative.md').read_text(encoding='utf-8')
        schema=agent.read(p/f"call-{m['final_call_index']:02d}.request.json")['tools'][-1]['function']['parameters']
        for field,size in (('question',61),('description',121)):
            bad=deepcopy(wire)
            if field=='question':bad[field]='字'*size
            else:bad['options'][0][field]='字'*size
            with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(bad,schema)
            with self.assertRaises(ValueError):agent.project_compact(bad,ctx,index,body,3)


if __name__=='__main__':unittest.main()
