"""Records, provenance and a process-safe single-runner lock."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import os
import uuid

PROJECT = Path(__file__).resolve().parents[2]
RESULTS = PROJECT/"results"
LOCAL_ZONE = timezone(timedelta(hours=8))

def now():
    return datetime.now(LOCAL_ZONE).isoformat(timespec="seconds")

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def json_default(obj):
    if isinstance(obj,Path): return str(obj)
    if hasattr(obj,"item"): return obj.item()
    if hasattr(obj,"tolist"): return obj.tolist()
    raise TypeError(type(obj).__name__)

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=json_default,allow_nan=False)+"\n",encoding="utf-8")
    tmp.replace(path)

def new_run(kind):
    RESULTS.mkdir(exist_ok=True)
    stamp=datetime.now(LOCAL_ZONE).strftime("%Y%m%d-%H%M%S")
    path=RESULTS/f"{stamp}-{kind}-{uuid.uuid4().hex[:6]}"
    path.mkdir()
    return path

def note(run_dir,message):
    with (Path(run_dir)/"run.log").open("a",encoding="utf-8") as f:
        f.write(f"{now()} {message}\n")
    print(message,flush=True)

@contextmanager
def runtime_lock():
    RESULTS.mkdir(exist_ok=True)
    f=(RESULTS/".runtime.lock").open("a+b")
    if f.tell()==0: f.write(b"1");f.flush()
    f.seek(0)
    try:
        if os.name=="nt":
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError as exc:
        f.close()
        raise RuntimeError("another teaching runner is using Virtual HIL") from exc
    try: yield
    finally:
        f.seek(0)
        if os.name=="nt":
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_UN)
        f.close()

def finalize(run_dir,manifest):
    manifest["completed_at"]=now()
    manifest["artifacts"]={
        p.relative_to(run_dir).as_posix():sha256(p)
        for p in sorted(Path(run_dir).rglob("*"))
        if p.is_file() and p!=Path(run_dir)/"manifest.json"
        and p.name!="verification.json" and not p.name.endswith(".tmp")
    }
    write_json(Path(run_dir)/"manifest.json",manifest)
    return manifest
