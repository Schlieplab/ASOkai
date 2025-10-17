from abc import ABC, abstractmethod


class Chemistry(ABC):
    """Abstract base class for antisense construct chemistry."""

    @property
    @abstractmethod
    def Smiles(self) -> str:
        """Return the chemistry SMILES"""
        pass


