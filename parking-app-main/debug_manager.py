#!/usr/bin/env python3
"""Debug script to check manager user setup"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User
from app.models.parking import ParkingLot

def debug_manager():
    app = create_app()
    with app.app_context():
        print("=== DEBUGGING MANAGER USER ===")
        
        # Check if manager user exists
        manager = User.query.filter_by(email='manager@example.com').first()
        print(f"Manager user found: {manager}")
        
        if manager:
            print(f"Manager ID: {manager.id}")
            print(f"Manager name: {manager.full_name}")
            print(f"Manager is_admin: {manager.is_admin}")
            print(f"Manager is_active: {manager.is_active}")
            
            # Check managed lots
            managed_lots = manager.managed_lots
            print(f"Managed lots count: {len(managed_lots)}")
            print(f"Managed lots: {[lot.name for lot in managed_lots]}")
            
            # Check if managed_lots evaluates to True/False
            print(f"managed_lots evaluates to: {bool(managed_lots)}")
        
        # Check all parking lots
        all_lots = ParkingLot.query.all()
        print(f"\n=== ALL PARKING LOTS ===")
        for lot in all_lots:
            print(f"Lot: {lot.name}, Manager ID: {lot.manager_id}")
            if lot.manager_id:
                manager_user = User.query.get(lot.manager_id)
                print(f"  Manager: {manager_user.email if manager_user else 'Not found'}")
        
        # Check all users
        print(f"\n=== ALL USERS ===")
        all_users = User.query.all()
        for user in all_users:
            lots_count = len(user.managed_lots)
            print(f"User: {user.email}, Admin: {user.is_admin}, Managed lots: {lots_count}")

if __name__ == '__main__':
    debug_manager()
