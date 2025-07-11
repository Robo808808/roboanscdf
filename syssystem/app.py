from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List
import subprocess
import json

app = FastAPI()

VALID_ROLES = {"SYSDBA", "SYSOPER", "SYSDG", "SYSBACKUP", "DBA"}

class DBARequest(BaseModel):
    dba_id: str = Field(..., example="123")
    roles: List[str] = Field(default=[])

def run_script(action: str, dba_id: str, roles: List[str] = None):
    cmd = ["./manage_dba_accounts.py", action, dba_id]
    if roles:
        cmd.append(",".join(roles))
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=result.stderr.strip() or "Script returned invalid output")

@app.get("/roles")
def get_valid_roles():
    return {"valid_roles": sorted(VALID_ROLES)}

@app.post("/create")
def create_user(req: DBARequest):
    for role in req.roles:
        if role.upper() not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Invalid role: {role}")
    return run_script("create", req.dba_id, [r.upper() for r in req.roles])

@app.post("/modify")
def modify_user(req: DBARequest):
    for role in req.roles:
        if role.upper() not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Invalid role: {role}")
    return run_script("modify", req.dba_id, [r.upper() for r in req.roles])

@app.post("/delete")
def delete_user(req: DBARequest):
    return run_script("delete", req.dba_id)
