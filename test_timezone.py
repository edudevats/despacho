"""
Test script to verify Mexico City timezone is working correctly.
Run this to confirm the timezone helper is functioning properly.
"""
from datetime import datetime
from utils.timezone_helper import now_mexico, MEXICO_TIMEZONE

print("=" * 60)
print("TIMEZONE TEST - Mexico City (America/Mexico_City)")
print("=" * 60)

# Test 1: Get current time in Mexico
mexico_time = now_mexico()
print(f"\n1. Current time in Mexico City:")
print(f"   {mexico_time}")
print(f"   ISO Format: {mexico_time.isoformat()}")
print(f"   Timezone: {mexico_time.tzinfo}")

# Test 2: Compare with UTC
utc_time = datetime.utcnow()
print(f"\n2. Current UTC time (for comparison):")
print(f"   {utc_time}")

# Test 3: Show timezone offset
offset = mexico_time.utcoffset()
hours = offset.total_seconds() / 3600
print(f"\n3. Timezone offset from UTC:")
print(f"   {offset} ({hours:+.1f} hours)")

# Test 4: Show expected vs actual
print(f"\n4. Expected behavior:")
print(f"   Mexico City is UTC-6 (CST)")
print(f"   Current offset: UTC{hours:+.1f}")
if abs(hours + 6) < 0.1:  # Should be -6
    print(f"   ✅ CORRECT - Using Mexico City timezone!")
else:
    print(f"   ❌ INCORRECT - Not using Mexico City timezone!")

print("\n" + "=" * 60)
print("Test completed")
print("=" * 60)
