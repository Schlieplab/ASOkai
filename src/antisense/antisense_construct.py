from abc import ABC, abstractmethod


class AntisenseConstruct(ABC):
    def __init__(self, id: str, locus: Locus, genome: Genome, **kwargs):
        self.id = id
        self.locus = locus
        self.genome = genome
        for key, value in kwargs.items():
            setattr(self, key, value)

    @abstractmethod
    def get_antisense_construct_type(self) -> str:
        pass