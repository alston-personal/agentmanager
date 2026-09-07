#!/usr/bin/env python3
"""Run Core #288 reconcile under the already-enrolled Oracle runner identity.

LeopardCat's runtime repository is readable/writable by the enrolled AgentOS runner
boundary; unlike Vendor, it does not require or authorize a sudo user transition.
The underlying reconcile code remains identical and request data still cannot choose
an executable, user, path, or argv.
"""
import reconcile_leopardcat_frontend as reconcile


def direct_identity(_user, argv, *, cwd=None):
    return reconcile.run(argv, cwd=cwd)


reconcile.as_user = direct_identity

if __name__ == "__main__":
    raise SystemExit(reconcile.main())
