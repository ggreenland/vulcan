"""
Fireplace controller abstraction.

Provides a clean interface for fireplace operations with two implementations:
- RealFireplaceController: Connects to actual fireplace via TCP
- SimulatedFireplaceController: In-memory simulation for development/testing
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.config import config
from app.fireplace import fireplace


@dataclass
class FireplaceStatus:
    power: bool
    flame_level: int
    burner2: bool
    pilot: bool


class FireplaceController(ABC):
    """Abstract base class for fireplace controllers."""

    @abstractmethod
    async def get_status(self) -> FireplaceStatus:
        pass

    @abstractmethod
    async def power_on(self) -> bool:
        pass

    @abstractmethod
    async def power_off(self) -> bool:
        pass

    @abstractmethod
    async def set_flame_level(self, level: int) -> bool:
        pass

    @abstractmethod
    async def burner2_on(self) -> bool:
        pass

    @abstractmethod
    async def burner2_off(self) -> bool:
        pass


class RealFireplaceController(FireplaceController):
    """Controller that communicates with the real fireplace via TCP."""

    async def get_status(self) -> FireplaceStatus:
        status = await fireplace.get_status()
        return FireplaceStatus(
            power=status.power,
            flame_level=status.flame_level,
            burner2=status.burner2,
            pilot=status.pilot,
        )

    async def power_on(self) -> bool:
        return await fireplace.power_on()

    async def power_off(self) -> bool:
        return await fireplace.power_off()

    async def set_flame_level(self, level: int) -> bool:
        return await fireplace.set_flame_level(level)

    async def burner2_on(self) -> bool:
        return await fireplace.burner2_on()

    async def burner2_off(self) -> bool:
        return await fireplace.burner2_off()


class SimulatedFireplaceController(FireplaceController):
    """Controller that simulates fireplace behavior in memory."""

    def __init__(self):
        self._state = FireplaceStatus(
            power=False,
            flame_level=50,
            burner2=False,
            pilot=True,
        )

    @property
    def state(self) -> FireplaceStatus:
        return self._state

    async def get_status(self) -> FireplaceStatus:
        return self._state

    async def power_on(self) -> bool:
        self._state.power = True
        return True

    async def power_off(self) -> bool:
        self._state.power = False
        return True

    async def set_flame_level(self, level: int) -> bool:
        self._state.flame_level = max(0, min(100, level))
        return True

    async def burner2_on(self) -> bool:
        self._state.burner2 = True
        return True

    async def burner2_off(self) -> bool:
        self._state.burner2 = False
        return True


# Singleton instances - created once at import time
_real_controller = RealFireplaceController()
_simulated_controller = SimulatedFireplaceController()


def get_controller() -> FireplaceController:
    """
    Dependency injection provider for fireplace controller.
    Returns controller based on FIREPLACE_CONTROLLER config.
    """
    if config.FIREPLACE_CONTROLLER == "simulated":
        return _simulated_controller
    return _real_controller
