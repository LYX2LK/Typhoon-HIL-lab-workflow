"""Numerical evidence, API failure and human approval boundary tests (offline)."""
from copy import deepcopy
import csv
import json
import math
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from typhoon_lab import boost_ai as ai
from typhoon_lab.config import load_config
from typhoon_lab.adapters.boost import BoostAdapter
from typhoon_lab.utils import write_json, finalize, sha256

ROOT=Path(__file__).resolve().parents[1]


class BoostAITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/"source";self.source.mkdir()
        c=load_config(ROOT/"configs/boost_vin_drop.json")
        with (self.source/"waveforms.csv").open("w",encoding="utf-8",newline="") as f:
            w=csv.writer(f);w.writerow(ai.COLUMNS)
            for k in range(15000):
                t=k/10000
                # Exact known slope before the event, then a known exponential recovery.
                y=49.5+t if t<.5 else 50-8*math.exp(-(t-.5)/.08)
                w.writerow([t,t,y,1,50,35 if t<.5 else 28])
        m=ai.analyze(self.source/"waveforms.csv",c)
        write_json(self.source/"config.json",c);write_json(self.source/"metrics.json",m)
        write_json(self.source/"capture.json",{})
        write_json(self.source/"events.json",{"schema_version":2,"planned":c["events"],"events":m["events"]})
        finalize(self.source,{"kind":"run","model":"boost_closed_loop","backend":"virtual_hil","status":m["status"],"events":m["events"],"event_schedule":BoostAdapter().describe_schedule(c)})
        self.request=ai.make_request([ai.summarize(self.source)])

    def answer(self,digest):
        return {"request_sha256":digest,"cause_status":"undetermined","summary":"下冲",
            "observations":[{"text":"峰值越限","evidence":["R1.metrics"]}],
            "hypotheses":[{"text":"启动叠加待检验","evidence":["R1.pre_event_trend"]}],
            "gaps":["缺PI内部状态"],"suggested_actions":[{"action_id":"late","purpose":"减弱启动混杂"}],"updated_interpretation":"待对照"}

    def completed(self):
        p=self.root/"analysis"
        def model(path,service):
            a=self.answer(sha256(path/"llm_request.json"))
            write_json(path/"answer.json",a)
            write_json(path/"http_response.json",{"choices":[{"message":{"content":json.dumps(a)}}]})
            call={"status":"completed","request_sha256":a["request_sha256"]}
            write_json(path/"model_call.json",call);return call
        with patch.object(ai,"call_model",side_effect=model): ai.analyze_boost([self.source],p,"mock-service")
        return p

    def test_actual_event_alignment_and_known_trend(self):
        s=ai.summarize(self.source)
        self.assertEqual(s["experiment_status"],"failed")
        self.assertEqual(s["record_status"],"passed")
        self.assertAlmostEqual(s["pre_event_trend"]["slope_v_per_s"],1.0,places=10)
        self.assertEqual(s["aligned_response"]["sample_count"],9000)
        self.assertAlmostEqual(s["aligned_response"]["peak_deviation_relative"],.16)

    def test_model_hash_and_evidence_and_actions_are_checked(self):
        a=self.answer("expected")
        for mutation in (lambda x:x.update(request_sha256="other"),lambda x:x.update(cause_status="confirmed"),
                         lambda x:x["observations"][0].update(evidence=["invented"]),
                         lambda x:x["suggested_actions"][0].update(action_id="powershell -command stop-process")):
            b=deepcopy(a);mutation(b)
            with self.assertRaises(ValueError): ai.validate_answer(b,self.request,"expected")

    def test_derived_record_recomputes_and_detects_raw_tampering(self):
        p=self.completed();self.assertEqual(ai.verify_ai(p)["record_status"],"passed")
        with (p/"sources/R1/waveforms.csv").open("a",encoding="utf-8") as f:f.write("corrupt\n")
        self.assertEqual(ai.verify_ai(p)["record_status"],"failed")

    def test_confirmation_denies_missing_token_and_config_change_before_runtime(self):
        p=self.completed();plan_dir=self.root/"plan"
        plan=ai.create_plan(p,"late",plan_dir)
        self.assertEqual({x["field"] for x in plan["differences"]},{"/events","/capture/duration_s","/acceptance/min_samples"})
        with patch("typhoon_lab.runtime.execute_case") as execute:
            with self.assertRaises(ValueError): ai.execute_plan(plan_dir,"","human")
            c=ai.read(plan_dir/"candidate_config.json");c["acceptance"]["max_deviation_relative"]=.2
            write_json(plan_dir/"candidate_config.json",c)
            with self.assertRaises(ValueError): ai.execute_plan(plan_dir,plan["confirmation_token"],"human")
            execute.assert_not_called()

    def test_human_choice_not_in_model_advice_is_labelled(self):
        p=self.completed();plan=ai.create_plan(p,"baseline",self.root/"plan")
        self.assertEqual(plan["selection_origin"],"experimenter_selection")

    def test_suggestions_follow_answer_subset_and_purpose_instead_of_static_menu(self):
        p=self.completed();guidance=ai.action_guidance(p)
        self.assertEqual([a["action_id"] for a in guidance["suggested_actions"]],["late"])
        self.assertEqual(guidance["suggested_actions"][0]["purpose"],"减弱启动混杂")
        self.assertEqual({a["action_id"] for a in guidance["other_actions"]},{"repeat","baseline"})
        plan=ai.create_plan(p,"late",self.root/"plan")
        self.assertEqual(plan["purpose"],"减弱启动混杂")
        self.assertEqual(plan["selection_origin"],"model_suggestion")

    def test_initial_report_does_not_claim_a_completed_comparison(self):
        p=self.completed();report=(p/"report.html").read_text(encoding="utf-8")
        self.assertIn("当前尚无对照结果",report)
        self.assertIn("首轮提供现象与候选解释",report)
        self.assertNotIn("本对照支持减弱",report)

    def test_model_advice_order_is_retained(self):
        p=self.completed()
        answer=ai.read(p/"answer.json")
        answer["suggested_actions"]=[{"action_id":"baseline","purpose":"先建立背景"},{"action_id":"late","purpose":"再延后比较"}]
        write_json(p/"answer.json",answer)
        write_json(p/"http_response.json",{"choices":[{"message":{"content":json.dumps(answer)}}]})
        finalize(p,ai.read(p/"manifest.json"))
        self.assertEqual([a["action_id"] for a in ai.action_guidance(p)["suggested_actions"]],["baseline","late"])

    def test_demo_requires_explicit_manual_choice_and_rejects_changed_confirmation(self):
        import shutil
        from typhoon_lab import boost_demo
        p=self.root/"results"/"analysis";p.parent.mkdir();shutil.copytree(self.completed(),p)
        session=self.root/"results"/"session";session.mkdir()
        write_json(session/"demo_state.json",{"busy":False,"session_dir":str(session),"message":"首次分析完成","first_ai":str(p)})
        with patch.object(boost_demo,"PROJECT",self.root): demo=boost_demo.Demo(session)
        self.assertEqual(demo.public_state()["action_guidance"]["suggested_actions"][0]["action_id"],"late")
        with self.assertRaises(ValueError):demo.launch("plan",{"action":"repeat"})
        demo.launch("plan",{"action":"repeat","manual_choice":True})
        self.assertEqual(demo.state["plan"]["selection_origin"],"experimenter_selection")
        with patch.object(boost_demo.threading,"Thread") as thread:
            with self.assertRaises(ValueError):demo.launch("confirm",{"approved":True,"operator":"human","action":"late"})
            thread.assert_not_called()
        demo.state["first_ai"]=str(self.root/"another-analysis")
        self.assertIsNone(demo.public_state()["action_guidance"])

    def test_demo_does_not_resume_busy_session(self):
        from typhoon_lab import boost_demo
        session=self.root/"results"/"session";session.mkdir(parents=True)
        write_json(session/"demo_state.json",{"busy":True,"session_dir":str(session)})
        with patch.object(boost_demo,"PROJECT",self.root),self.assertRaisesRegex(ValueError,"marked busy"):
            boost_demo.Demo(session)

    def test_api_http_error_is_recorded_without_key_or_fabricated_answer(self):
        p=self.root/"api";p.mkdir();write_json(p/"llm_request.json",self.request)
        s={"base_url":"https://example.invalid","model":"model","provider":"mock","timeout_s":1,"max_tokens":1000}
        class Opener:
            def open(self,*a,**kw):raise urllib.error.HTTPError("url",403,"secret-token",{},None)
        with patch.object(ai,"load_service",return_value=(s,"secret-token")),patch.object(ai.urllib.request,"build_opener",return_value=Opener()):
            call=ai.call_model(p,"service")
        self.assertEqual(call["status"],"error");self.assertEqual(call["error"]["http_status"],403)
        self.assertFalse((p/"answer.json").exists())
        for f in p.iterdir(): self.assertNotIn("secret-token",f.read_text(encoding="utf-8"))

    def test_timeout_and_blank_or_truncated_json_fail_closed(self):
        s={"base_url":"https://example.invalid","model":"model","provider":"mock","timeout_s":1,"max_tokens":1000}
        for response in ({"choices":[{"finish_reason":"stop","message":{"content":" "}}]},
                         {"choices":[{"finish_reason":"length","message":{"content":"{}"}}]}):
            p=self.root/("api"+str(len(list(self.root.iterdir()))));p.mkdir();write_json(p/"llm_request.json",self.request)
            class Response:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def read(self,*args):return json.dumps(response).encode("utf-8")
            class Opener:
                def open(self,*args,**kwargs):return Response()
            with patch.object(ai,"load_service",return_value=(s,"secret-token")),patch.object(ai.urllib.request,"build_opener",return_value=Opener()):
                self.assertEqual(ai.call_model(p,"service")["status"],"error")
            self.assertFalse((p/"answer.json").exists())

    def test_comparison_rejects_changed_threshold_or_event_amplitude(self):
        a=ai.summarize(self.source)
        for field in ("threshold","amplitude"):
            b=deepcopy(a)
            if field=="threshold":b["config"]["acceptance"]["max_deviation_relative"]=.2
            else:b["config"]["events"][0]["value"]=29
            with self.assertRaises(ValueError):ai.compare_conditions([a,b])

    def test_confirmed_plan_keeps_byte_hash_across_json_roundtrip(self):
        p=self.completed();pd=self.root/"plan";plan=ai.create_plan(p,"repeat",pd)
        confirmation={"confirmed_by":"test human","plan_sha256":sha256(pd/"plan.json"),"config_sha256":plan["config_sha256"]}
        write_json(pd/"confirmation.json",confirmation);write_json(pd/"execution.json",{"confirmation":confirmation})
        provenance=ai.confirmation_from_plan(pd)
        ai.check_confirmation(provenance,self.source,self.source,p)
        provenance["plan"]["action_id"]="late"
        with self.assertRaises(ValueError):ai.check_confirmation(provenance,self.source,self.source,p)

    def test_timeout_is_saved_and_does_not_create_answer(self):
        p=self.root/"timeout";p.mkdir();write_json(p/"llm_request.json",self.request)
        s={"base_url":"https://example.invalid","model":"model","provider":"mock","timeout_s":1,"max_tokens":1000}
        class Opener:
            def open(self,*args,**kwargs):raise TimeoutError("sensitive exception text")
        with patch.object(ai,"load_service",return_value=(s,"secret")),patch.object(ai.urllib.request,"build_opener",return_value=Opener()):
            call=ai.call_model(p,"service")
        self.assertEqual(call["error"]["type"],"TimeoutError");self.assertFalse((p/"answer.json").exists())
        self.assertNotIn("sensitive exception text",(p/"model_call.json").read_text(encoding="utf-8"))


if __name__=="__main__":unittest.main()
