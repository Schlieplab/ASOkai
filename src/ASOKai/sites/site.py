from abc import ABC, abstractmethod
from Bio.Seq import Seq
from typing import Dict, Any
from ..utils import Serializable


class Site(Serializable, ABC):
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
    
    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, Seq):
            return {
                '__type__': 'Bio.Seq.Seq',
                'sequence': str(value)
            }
        return super()._serialize_value(value)

    @classmethod
    def _deserialize_value(cls, value_data: Any) -> Any:
        if isinstance(value_data, dict) and value_data.get('__type__') == 'Bio.Seq.Seq':
            return Seq(value_data['sequence'])
        return super()._deserialize_value(value_data)

    @classmethod
    def _get_init_arg_name_map(cls) -> Dict[str, str]:
        return {"_sequence": "sequence"}
    