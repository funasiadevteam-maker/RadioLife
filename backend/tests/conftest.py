"""Session-wide test config: force Stripe to mock mode.

Phase 36e Item #3 flipped STRIPE_MODE=live in /app/backend/.env. Unit tests
must NEVER hit the network.

`core/config.py:9` calls `load_dotenv(override=True)` which clobbers any
STRIPE_MODE we set in env. Touching core/config.py is out of scope for the
Phase 19b sweep. We work around by monkey-patching `services.stripe_client`
so its `is_live()` always returns False regardless of env state.
"""
import os
import sys

# Ensure pre-import env state is also mock (belt + braces).
os.environ["STRIPE_MODE"] = "mock"

# Eagerly import + patch BEFORE any test module loads server.
sys.path.insert(0, "/app/backend")
import services.stripe_client as _sc

_sc.is_live = lambda: False
_sc.stripe_mode = lambda: "mock"
