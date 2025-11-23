#!/usr/bin/env python3
"""
Script to test GPM Profile Manager - import functions from gpm_profile module
"""

from gpm_profile import (
    get_profiles_list,
    find_profile_by_name,
    create_profile,
    find_or_create_profile,
    start_profile,
    BASE_URL
)

if __name__ == "__main__":
    print("=" * 70)
    print("FULL TEST: Find/Create Profile, Start It and Get WebDriver")
    print("=" * 70)
    
    profile_name = "haNguyen"
    driver = None
    
    # Step 1: Find or create profile
    print("\n[STEP 1] Finding or creating profile...")
    print("=" * 70)
    profile = find_or_create_profile(profile_name)
    
    if profile is None:
        print("\n❌ Failed to find or create profile. Exiting...")
        exit(1)
    
    profile_id = profile.get('id')
    
    # Step 2: Start the profile and get WebDriver
    print("\n[STEP 2] Starting profile and creating WebDriver...")
    print("=" * 70)
    
    # Define window dimensions
    win_width = 1280
    win_height = 720
    pos_x = 300
    pos_y = 300
    
    driver = start_profile(
        profile_id=profile_id,
        win_width=win_width,
        win_height=win_height,
        pos_x=pos_x,
        pos_y=pos_y
    )
    
    # Step 3: Summary
    print("\n")
    print("=" * 70)
    print("Summary:")
    print(f"  Profile Name: {profile_name}")
    print(f"  Profile ID: {profile_id}")
    print(f"  Find/Create: {'✓ SUCCESS' if profile is not None else '✗ FAILED'}")
    print(f"  WebDriver: {'✓ SUCCESS' if driver is not None else '✗ FAILED'}")
    
    if driver:
        print(f"\n  ✓ WebDriver is ready!")
        print(f"  - You can now use the driver to automate browser tasks")
        print(f"  - Example: driver.get('https://example.com')")
        
        # Keep the browser open for demonstration (optional)
        print(f"\n  Browser will stay open. Press Ctrl+C to close...")
        try:
            import time
            time.sleep(5)  # Keep browser open for 5 seconds
        except KeyboardInterrupt:
            print("\n  Closing browser...")
            driver.quit()
    else:
        print(f"\n  ❌ Failed to create WebDriver")
    
    print("=" * 70)
