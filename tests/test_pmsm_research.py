"""Research proposals cannot change the score or bypass executable boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from typhoon_lab.pmsm_research import load_problem, proposal_config, random_proposal, verify_research
from typhoon_lab.research_model import call_json
from typhoon_lab.utils import PROJECT, write_json, finalize


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.problem, self.template = load_problem(PROJECT / 'configs/pmsm_search_pilot.json')
        self.answer = {'hypothesis': '负载先行可能改变恢复过程', 'feedback_used': '首轮基于控制结构',
                       'expected_response': '比较恢复时间和累计误差', 'feedback_rounds': [],
                       'candidate': {'target_speed_rpm': 900, 'load_nm': .03, 'order': 'load_then_speed', 'gap_ms': 20}}

    def test_deceleration_is_executable_and_template_score_is_preserved(self):
        c = proposal_config(self.answer, self.problem, self.template, [])
        self.assertEqual(c['events'][0]['target'], 'load_torque_nm')
        self.assertEqual(c['events'][1]['value'], 900)
        self.assertAlmostEqual(c['events'][1]['at_s'], .32)
        self.assertEqual(c['acceptance'], self.template['acceptance'])

    def test_proposal_cannot_override_judgment_or_read_future_feedback(self):
        for field, value in [('acceptance', {'max_speed_error_rpm': 200}), ('script', 'pass')]:
            bad = deepcopy(self.answer); bad[field] = value
            with self.assertRaises(ValueError): proposal_config(bad, self.problem, self.template, [])
        for refs in [[], [2], [True]]:
            bad = deepcopy(self.answer); bad['feedback_rounds'] = refs
            with self.assertRaises(ValueError): proposal_config(bad, self.problem, self.template, [{'round': 1}])
        self.answer['feedback_rounds'] = [1]
        proposal_config(self.answer, self.problem, self.template, [{'round': 1}])

    def test_rejects_boolean_nonfinite_offgrid_and_mismatched_simultaneous(self):
        for key, value in [('load_nm', True), ('load_nm', float('nan')), ('target_speed_rpm', 5000), ('gap_ms', 20.001)]:
            bad = deepcopy(self.answer); bad['candidate'][key] = value
            with self.assertRaises(ValueError): proposal_config(bad, self.problem, self.template, [])
        bad = deepcopy(self.answer); bad['candidate']['order'] = 'simultaneous'
        with self.assertRaises(ValueError): proposal_config(bad, self.problem, self.template, [])

    def test_random_baseline_is_repeatable_and_uses_same_validator(self):
        a, b = random.Random(73), random.Random(73)
        for _ in range(10):
            x = random_proposal(a, self.problem, [])
            self.assertEqual(x, random_proposal(b, self.problem, []))
            proposal_config(x, self.problem, self.template, [])


class TransportTests(unittest.TestCase):
    def test_incomplete_raw_response_is_saved_without_retry_or_credentials(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size): return json.dumps({'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]}).encode()
        class Opener:
            calls = 0
            def open(self, *args, **kwargs):
                self.calls += 1
                return Response()
        opener = Opener()
        service = {'base_url': 'https://example.invalid', 'model': 'test', 'timeout_s': 5, 'max_tokens': 10,
                   'api_key_env': 'SECRET_ENV', 'env_file': 'secret.local'}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'call'
            with (patch('typhoon_lab.research_model.load_service', return_value=(service, 'private-key-value')),
                  patch('typhoon_lab.research_model.urllib.request.build_opener', return_value=opener)):
                with self.assertRaises(RuntimeError): call_json(output, 'unused', 'system', {'task': 'test'})
            self.assertEqual(opener.calls, 1)
            self.assertTrue((output / 'http_response.json').is_file())
            for path in output.iterdir():
                self.assertNotIn('private-key-value', path.read_text(encoding='utf-8'))
            self.assertEqual(json.loads((output / 'model_call.json').read_text(encoding='utf-8'))['status'], 'error')


class FeedbackBindingTests(unittest.TestCase):
    def test_invalid_proposals_are_part_of_history_and_semantic_tampering_is_detected(self):
        problem, template = load_problem(PROJECT / 'configs/pmsm_search_pilot.json')
        history = []
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            write_json(output / 'problem.json', problem); write_json(output / 'template.json', template)
            rows = []
            for step in (1, 2):
                folder = output / f'round-{step:02d}'
                proposal = random_proposal(random.Random(step), problem, history)
                proposal['candidate']['target_speed_rpm'] = 9999
                error = 'target_speed_rpm outside frozen problem range'
                write_json(folder / 'proposal.json', proposal)
                write_json(folder / 'decision_input.json', {'history': deepcopy(history)})
                rows.append({'round': step, 'status': 'invalid_proposal', 'validation_error': error})
                history.append({'round': step, 'candidate': proposal['candidate'], 'status': 'invalid_proposal', 'error': error})
            manifest = {'kind': 'pmsm_research', 'mode': 'search', 'strategy': 'random', 'status': 'failed', 'rounds': rows, 'sources': []}
            finalize(output, manifest)
            self.assertEqual(verify_research(output)['record_status'], 'passed')
            write_json(output / 'round-02/decision_input.json', {'history': []})
            finalize(output, manifest)
            self.assertIn('decision input differs from actual preceding feedback', verify_research(output)['record_problems'])
            manifest['analysis_method_version'] = 999
            finalize(output, manifest)
            self.assertIn('recomputation skipped for unsupported version', verify_research(output)['record_problems'])


if __name__ == '__main__': unittest.main()
