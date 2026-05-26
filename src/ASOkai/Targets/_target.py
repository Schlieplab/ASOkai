#!/usr/bin/env python
"""
Filename: src/ASOkai/Targets/target.py
Author: Arash Ayat
Copyright: 2025, Alexander Schliep
Version: 0.1.0
Description: This file defines the base Target class.
License: LGPL-3.0-or-later
"""
from abc import ABC
from typing import Dict, List, Optional

from ..Sites import Site
from ..Utils import Serializable


class Target(Serializable, ABC):
    """
    Abstract base class for candidate target.
    """
    def __init__(self, 
                 id: str, 
                 sites: Optional[Dict[str, Site]] = None, 
                 **kwargs):
        """
        Initializes a `CandidateTarget` object.
        
        Args:
            id: The ID of the target.
            sites: The target sites of the target. Defaults to an empty dict if not provided.
            **kwargs: Additional keyword arguments.
        """
        self.id = id
        
        Serializable.__init__(self, **kwargs)
        
        self._sites: Dict[str, Site] = sites if sites is not None else {}
    
        
    def site_by_id(self, id: str) -> Site:
        """
        Get a target site by its ID.
        
        Args:
            id: The ID of the target site.
        """
        if id not in self._sites:
            raise ValueError(f"Target site with ID '{id}' not found.")
        
        return self._sites[id]
    
    def add_site(self, site: Site) -> None:
        """
        Add a target site to the collection.
        
        Args:
            site: The site to add.
        
        Raises:
            ValueError: If a site with the same ID already exists.
        """
        if site.id in self._sites:
            raise ValueError(f"Target site with ID '{site.id}' already exists.")
        
        self._sites[site.id] = site
    
    def remove_site(self, id: str) -> None:
        """
        Remove a target site by its ID.
        
        Args:
            id: The ID of the target site to remove.
        
        Raises:
            ValueError: If no site with the given ID exists.
        """
        if id not in self._sites:
            raise ValueError(f"Target site with ID '{id}' not found.")
        
        del self._sites[id]
    
    @property
    def sites(self) -> List[Site]:
        """
        Get all target sites as a list.
        """
        return list(self._sites.values())
        
