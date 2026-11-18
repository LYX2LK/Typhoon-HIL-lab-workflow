"""Small JSON model transport for research tasks, independent of demo Agents."""
import json
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request

from .utils import PROJECT, now, sha256, write_json


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('model redirect rejected')


def load_service(path):
    service = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    url = urllib.parse.urlsplit(service['base_url'])
    if url.username or url.password or url.query or url.fragment:
        raise ValueError('service URL contains credentials, query or fragment')
    if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1')):
        raise ValueError('service requires HTTPS or loopback HTTP')
    if not 1 <= service['timeout_s'] <= 180:
        raise ValueError('service timeout outside 1..180 seconds')
    key = os.environ.get(service['api_key_env'], '').strip()
    env_path = PROJECT / service.get('env_file', 'demo.env.local')
    if not key and env_path.is_file():
        for line in env_path.read_text(encoding='utf-8-sig').splitlines():
            if line.strip().startswith(service['api_key_env'] + '='):
                key = line.split('=', 1)[1].strip().strip('"').strip("'")
    if not key:
        raise ValueError('configured model credential is unavailable')
    return service, key


def call_json(output, service_path, system, request):
    """Save the actual response before parsing; no automatic repair or retry."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'input.json', request)
    metadata = {'started_at': now(), 'status': 'error', 'input_sha256': sha256(output / 'input.json')}
    timer = time.monotonic()
    try:
        service, key = load_service(service_path)
        public = {k: v for k, v in service.items() if k not in ('api_key_env', 'env_file')}
        write_json(output / 'service.json', public)
        payload = {'model': service['model'], 'stream': False, 'max_tokens': service['max_tokens'],
                   'temperature': service.get('temperature', 0), 'response_format': {'type': 'json_object'},
                   'messages': [{'role': 'system', 'content': system},
                                {'role': 'user', 'content': json.dumps(request, ensure_ascii=False)}]}
        if 'thinking' in service:
            payload['thinking'] = service['thinking']
        write_json(output / 'http_request.json', payload)
        req = urllib.request.Request(service['base_url'].rstrip('/') + '/chat/completions',
              data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
              headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=service['timeout_s']) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError('model response exceeds limit')
        (output / 'http_response.json').write_bytes(raw)
        value = json.loads(raw.decode('utf-8'))
        choice = value['choices'][0]
        metadata.update(response_id=value.get('id'), returned_model=value.get('model'),
                        usage=value.get('usage'), finish_reason=choice.get('finish_reason'))
        if choice.get('finish_reason') != 'stop':
            raise ValueError('model response incomplete')
        answer = json.loads(choice['message']['content'])
        if not isinstance(answer, dict):
            raise ValueError('model response must be a JSON object')
        write_json(output / 'answer.json', answer)
        metadata['status'] = 'completed'
    except Exception as exc:
        # Exceptions/HTTP bodies can echo credentials. Persist only safe classifications.
        metadata['error'] = {'type': type(exc).__name__, 'http_status': getattr(exc, 'code', None)}
        raise RuntimeError('model call failed; inspect local model_call.json and saved response') from None
    finally:
        metadata.update(completed_at=now(), elapsed_s=time.monotonic() - timer)
        write_json(output / 'model_call.json', metadata)
    return answer
