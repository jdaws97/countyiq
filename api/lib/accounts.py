"""CountyIQ account/membership resolution; external identities are replaceable."""
from uuid import uuid4
from fastapi import HTTPException
from api.lib.auth import Identity, require_identity


def lookup_account(cur, identity: Identity):
    cur.execute("""SELECT u.user_id,u.email,w.workspace_id,w.version
        FROM public.app_identities i JOIN public.app_users u USING(user_id)
        LEFT JOIN public.watchspaces w ON w.owner_user_id=u.user_id
        WHERE i.provider=%s AND i.issuer=%s AND i.subject=%s""",
        (identity.provider,identity.issuer,identity.subject))
    return cur.fetchone()


def provision_account(cur, identity: Identity):
    # Two tabs signing in simultaneously create one account and personal workspace.
    key = "|".join((identity.provider,identity.issuer,identity.subject))
    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 561056))", (key,))
    row = lookup_account(cur, identity)
    if row is None:
        user_id = str(uuid4())
        cur.execute("INSERT INTO public.app_users(user_id,email) VALUES (%s,%s)",(user_id,identity.email))
        cur.execute("INSERT INTO public.app_identities(provider,issuer,subject,user_id) VALUES (%s,%s,%s,%s)",
            (identity.provider,identity.issuer,identity.subject,user_id))
    else:
        user_id = row["user_id"]
    if row is None or row["workspace_id"] is None:
        workspace_id = str(uuid4())
        cur.execute("INSERT INTO public.watchspaces(workspace_id,owner_user_id) VALUES (%s,%s)",(workspace_id,user_id))
        cur.execute("INSERT INTO public.workspace_members(workspace_id,user_id,role) VALUES (%s,%s,'owner')",(workspace_id,user_id))
    return lookup_account(cur,identity)


def account_workspace(cur, request, *, lock=False):
    identity = require_identity(request)
    cur.execute("""SELECT i.user_id,w.workspace_id,w.version,w.saved_searches,w.comparison,w.recent_investigations,m.role
        FROM public.app_identities i
        JOIN public.workspace_members m USING(user_id)
        JOIN public.watchspaces w USING(workspace_id)
        WHERE i.provider=%s AND i.issuer=%s AND i.subject=%s AND w.owner_user_id=i.user_id""" +
        (" FOR UPDATE OF w" if lock else ""),
        (identity.provider,identity.issuer,identity.subject))
    row = cur.fetchone()
    if not row:
        raise HTTPException(409, "Initialize your signed-in workspace first")
    if request.headers.get("x-countyiq-user") != str(row["user_id"]):
        raise HTTPException(401, "Account changed; reload your workspace")
    return row
