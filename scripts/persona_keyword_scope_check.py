"""Read-only account-bound Threads search OAuth scope diagnosis.

Never print or persist credentials, external posts, provider IDs, or raw errors.
"""
import json
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from scripts.persona_social_executor import CREDS, find_binding

def check_keyword_scope(*, credentials_path=CREDS, opener=None):
    out={"schema":"agentos.mio-keyword-scope-check/v1","status":"BLOCKED",
         "account":"mio.milkcat","operation":"debug_token","write_performed":False}
    try:
        store=json.loads(Path(credentials_path).read_text(encoding="utf-8"))
        binding_id,binding=find_binding(store,"mio.milkcat")
        if not binding_id or not binding or ":persona:" not in binding_id:
            return {**out,"reason":"ACCOUNT_BINDING_UNVERIFIED"}
        token=binding.get("access_token")
        if not isinstance(token,str) or not token:
            return {**out,"reason":"TOKEN_UNAVAILABLE"}
        args=urllib.parse.urlencode({"input_token":token})
        req=urllib.request.Request("https://graph.threads.net/debug_token?"+args,
              headers={"Authorization":"Bearer "+token,"Accept":"application/json"})
        handler=opener or urllib.request.urlopen
        with handler(req,timeout=15) as response:
            payload=json.loads(response.read(65536).decode("utf-8"))
        data=payload.get("data") if isinstance(payload,dict) else None
        if not isinstance(data,dict):
            return {**out,"reason":"PROVIDER_RESPONSE_INVALID"}
        if data.get("is_valid") is not True:
            return {**out,"reason":"TOKEN_NOT_CONFIRMED_VALID"}
        scopes=data.get("scopes")
        if not isinstance(scopes,list):
            return {**out,"reason":"SCOPES_UNAVAILABLE"}
        granted="threads_keyword_search" in scopes
        return {**out,"status":"PASS","reason":"GRANTED" if granted else "NOT_GRANTED",
                "keyword_search_granted":granted}
    except urllib.error.HTTPError as exc:
        return {**out,"reason":"PROVIDER_HTTP_"+str(exc.code)}
    except (OSError,TypeError,ValueError,KeyError,UnicodeError):
        return {**out,"reason":"DIAGNOSTIC_UNAVAILABLE"}

if __name__=="__main__":
    print(json.dumps(check_keyword_scope(),sort_keys=True))
