#!/usr/bin/env python
"""
Filename: src/ASOKai/targets/target.py
Author: Arash Ayat
Copyright: 2025, Alexander Schliep
Version: 0.1.0
Description: This file defines the base Target class.
License: LGPL-3.0-or-later
"""
from abc import ABC, abstractmethod
from ..sites import Site
from typing import Dict, List
from ..utils import Serializable


class Target(Serializable, ABC):
    """
    Abstract base class for candidate target.
    """
    def __init__(self, 
                 id: str, 
                 target_sites: Dict[str, Site], 
                 **kwargs):
        """
        Initializes a `CandidateTarget` object.
        
        Args:
            id: The ID of the target.
            name: The name of the target.
            target_sites: The target sites of the target.
            **kwargs: Additional keyword arguments.
        """
        self.id = id
        
        for key, value in kwargs.items():
            setattr(self, key, value)
        
        self._target_sites: Dict[str, Site] = target_sites
    
        
    def site_by_id(self, id: str) -> Site:
        """
        Get a target site by its ID.
        
        Args:
            id: The ID of the target site.
        """
        if id not in self._target_sites:
            raise ValueError(f"Target site with ID '{id}' not found.")
        
        return self._target_sites[id]
    
    @property
    def sites(self) -> List[Site]:
        """
        Get all target sites.
        """
        return list(self._target_sites.values())
        
    @classmethod
    def _get_init_arg_name_map(cls) -> Dict[str, str]:
        return {"_target_sites": "target_sites"}
        
