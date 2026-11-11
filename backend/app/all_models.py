"""Import every module's ORM models so they register on Model.metadata before
any FK resolution or mapper configuration happens.

Needed by both Alembic migrations and the arq worker process: neither imports
the full FastAPI app (main.py), which is what would otherwise trigger this as
a side effect of loading every API router. Importing this module is the one
place that list needs to stay current as new modules are added.
"""

from app.modules.audit import models as _audit_models  # noqa: F401
from app.modules.auth import models as _auth_models  # noqa: F401
from app.modules.automations import models as _automations_models  # noqa: F401
from app.modules.bases import models as _bases_models  # noqa: F401
from app.modules.batch_submit import models as _batch_submit_models  # noqa: F401
from app.modules.bulk_ops import models as _bulk_ops_models  # noqa: F401
from app.modules.connectors import models as _connectors_models  # noqa: F401
from app.modules.dashboards import models as _dashboards_models  # noqa: F401
from app.modules.missing_terms import models as _missing_terms_models  # noqa: F401
from app.modules.notifications import models as _notifications_models  # noqa: F401
from app.modules.record_submit import models as _record_submit_models  # noqa: F401
from app.modules.row_policies import models as _row_policies_models  # noqa: F401
from app.modules.snapshots import models as _snapshots_models  # noqa: F401
from app.modules.workspaces import models as _workspaces_models  # noqa: F401
