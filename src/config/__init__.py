"""The app's settings, by concern, all reachable as `config.<NAME>` (`from src import config`).

Each module holds one concern: `paths` (files), `models` (models, budgets, prices), `limits`
(lengths, ranges, the calorie floor, the tool loop), `messages` (the disclaimer and fixed texts),
`environment` (keys, sign-in, demo mode, logging and tracing, and the only functions that read
secrets.toml or the environment), `knowledge` (the knowledge base and its search), `nutrition`
(the energy tools, the USDA table and API), `training` (the workout log), `evaluation`, `review`
(the weekly review) and `ui`. A name is defined in one module only (tests/test_config_package.py).

Code reads a setting through the package (`config.CHUNK_SIZE`), so a test patches it there. The
functions in `environment` call each other directly (e.g. `tracing_demo_unmasked()` calls
`demo_mode()`), so a test patches such a function on `config.environment` too, through
`tests.fakes.patch_config()`.
"""

from src.config.environment import *  # noqa: F403
from src.config.evaluation import *  # noqa: F403
from src.config.knowledge import *  # noqa: F403
from src.config.limits import *  # noqa: F403
from src.config.messages import *  # noqa: F403
from src.config.models import *  # noqa: F403
from src.config.nutrition import *  # noqa: F403
from src.config.paths import *  # noqa: F403
from src.config.review import *  # noqa: F403
from src.config.training import *  # noqa: F403
from src.config.ui import *  # noqa: F403
