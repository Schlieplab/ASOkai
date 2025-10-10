from abc import ABC, abstractmethod
from Bio.Seq import Seq


class Site(ABC):
    """Abstract base class for sites that may or may not be genomic."""

    def __init__(self,
                 id: str,
                 sequence: Seq = None,
                 **kwargs):
        """
        Initializes a Site object.

        Args:
            id: The ID of the site.
            sequence: The sequence of the site.
            kwargs: Additional keyword arguments.
        """
        
        self.id = id
        self._sequence = sequence
        
        for key, value in kwargs.items():
            setattr(self, key, value)

    @property
    def sequence(self) -> Seq:
        return self._sequence
    

    @abstractmethod
    def __repr__(self):
        """Return a string representation of this site."""
        pass
    