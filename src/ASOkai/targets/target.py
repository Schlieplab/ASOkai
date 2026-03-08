#!/usr/bin/env python
"""
Filename: src/ASOkai/targets/target.py
Author: Arash Ayat
Copyright: 2025, Alexander Schliep
Version: 0.1.0
Description: This file defines the base Target class.
License: LGPL-3.0-or-later
"""
from abc import ABC
from re import L
from ..sites import Site
from typing import Dict, List
from ..utils import Serializable


class Target(Serializable, ABC):
    """
    Abstract base class for candidate target.
    """
    def __init__(self, 
                 id: str, 
                 sites: Dict[str, Site], 
                 **kwargs):
        """
        Initializes a `CandidateTarget` object.
        
        Args:
            id: The ID of the target.
            sites: The target sites of the target.
            **kwargs: Additional keyword arguments.
        """
        self.id = id
        
        Serializable.__init__(self, **kwargs)
        
        self._sites: Dict[str, Site] = sites
    
        
    def site_by_id(self, id: str) -> Site:
        """
        Get a target site by its ID.
        
        Args:
            id: The ID of the target site.
        """
        if id not in self._sites:
            raise ValueError(f"Target site with ID '{id}' not found.")
        
        return self._sites[id]
    
    
    
    @property
    def sites(self) -> List[Site]:
        """
        Get all target sites as a list.
        """
        return list(self._sites.values())
        
