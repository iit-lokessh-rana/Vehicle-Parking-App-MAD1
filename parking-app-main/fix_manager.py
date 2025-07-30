#!/usr/bin/env python3
"""Fix script to properly assign manager to parking lot"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User
from app.models.parking import ParkingLot

def fix_manager_assignment():
    app = create_app()
    with app.app_context():
        print("=== FIXING MANAGER ASSIGNMENT ===")
        
        # Get manager user
        manager = User.query.filter_by(email='manager@example.com').first()
        if not manager:
            print("ERROR: Manager user not found!")
            return
        
        print(f"Found manager: {manager.email} (ID: {manager.id})")
        
        # Get parking lot
        lot = ParkingLot.query.filter_by(name='Downtown Garage').first()
        if not lot:
            print("ERROR: Downtown Garage parking lot not found!")
            return
        
        print(f"Found parking lot: {lot.name} (ID: {lot.id})")
        print(f"Current manager_id: {lot.manager_id}")
        
        # Assign manager to lot
        lot.manager_id = manager.id
        db.session.commit()
        
        print(f"✅ FIXED: Assigned manager {manager.email} to lot {lot.name}")
        
        # Verify the fix
        manager.managed_lots  # Refresh the relationship
        db.session.refresh(manager)
        db.session.refresh(lot)
        
        print(f"Verification:")
        print(f"  - Lot manager_id: {lot.manager_id}")
        print(f"  - Manager managed_lots count: {len(manager.managed_lots)}")
        print(f"  - Manager managed_lots: {[l.name for l in manager.managed_lots]}")
        print(f"  - managed_lots evaluates to: {bool(manager.managed_lots)}")

if __name__ == '__main__':
    fix_manager_assignment()
