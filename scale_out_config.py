"""
Scale-Out Profit Taking Configuration
======================================
Defines multiple TP levels and partial close percentages for different trading profiles.

Usage:
    from scale_out_config import SCALE_OUT_PROFILES, get_scale_out_config
    
    config = get_scale_out_config("aggressive")
    # Returns: {"enabled": True, "levels": [...]}
"""

# =============================================================================
# SCALE-OUT PROFILES
# =============================================================================

SCALE_OUT_PROFILES = {
    # -------------------------------------------------------------------------
    # AGGRESSIVE: Quick Profit Taking (Recommended for volatile markets)
    # -------------------------------------------------------------------------
    "aggressive": {
        "enabled": True,
        "description": "Quick profit taking - lock gains early, reduce risk fast",
        "levels": [
            {
                "r_mult": 1.0,      # At 1.0× Risk reward
                "close_pct": 0.33,  # Close 33% of position
                "label": "P1"       # Stage identifier
            },
            {
                "r_mult": 1.5,
                "close_pct": 0.33,  # Close 33% more (66% total closed)
                "label": "P2"
            },
            {
                "r_mult": 2.0,
                "close_pct": 0.34,  # Close remaining 34% (100% closed)
                "label": "P3"
            }
        ]
    },
    
    # -------------------------------------------------------------------------
    # CONSERVATIVE: Let Winners Run (Recommended for trending markets)
    # -------------------------------------------------------------------------
    "conservative": {
        "enabled": True,
        "description": "Let winners run - maximize profit potential with trailing stop",
        "levels": [
            {
                "r_mult": 1.5,
                "close_pct": 0.25,  # Close 25%
                "label": "P1"
            },
            {
                "r_mult": 2.5,
                "close_pct": 0.25,  # Close 25% more (50% total)
                "label": "P2"
            },
            {
                "r_mult": 4.0,
                "close_pct": 0.50,  # Close final 50% (or use trailing stop)
                "label": "P3"
            }
        ]
    },
    
    # -------------------------------------------------------------------------
    # BALANCED: Middle Ground (Default recommended)
    # -------------------------------------------------------------------------
    "balanced": {
        "enabled": True,
        "description": "Balanced approach - secure profit while allowing upside",
        "levels": [
            {
                "r_mult": 1.2,
                "close_pct": 0.30,  # Close 30%
                "label": "P1"
            },
            {
                "r_mult": 2.0,
                "close_pct": 0.35,  # Close 35% more
                "label": "P2"
            },
            {
                "r_mult": 3.0,
                "close_pct": 0.35,  # Close final 35%
                "label": "P3"
            }
        ]
    },
    
    # -------------------------------------------------------------------------
    # SCALPER: Very Quick Exits (For high-frequency trading)
    # -------------------------------------------------------------------------
    "scalper": {
        "enabled": True,
        "description": "Ultra-fast profit taking for scalping strategies",
        "levels": [
            {
                "r_mult": 0.5,
                "close_pct": 0.50,  # Close 50% early!
                "label": "P1"
            },
            {
                "r_mult": 1.0,
                "close_pct": 0.30,  # Close 30% more
                "label": "P2"
            },
            {
                "r_mult": 1.5,
                "close_pct": 0.20,  # Close remaining
                "label": "P3"
            }
        ]
    },
    
    # -------------------------------------------------------------------------
    # DISABLED: Single TP (Backwards compatibility)
    # -------------------------------------------------------------------------
    "disabled": {
        "enabled": False,
        "description": "Traditional single TP - all or nothing exit",
        "levels": []
    }
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_scale_out_config(profile_name="balanced"):
    """
    Get scale-out configuration by profile name.
    
    Args:
        profile_name (str): Name of profile ("aggressive", "conservative", "balanced", "scalper", "disabled")
    
    Returns:
        dict: Configuration with "enabled" and "levels" keys
        
    Example:
        >>> config = get_scale_out_config("aggressive")
        >>> print(config["levels"][0])
        {"r_mult": 1.0, "close_pct": 0.33, "label": "P1"}
    """
    if profile_name not in SCALE_OUT_PROFILES:
        print(f"⚠️ Unknown scale-out profile '{profile_name}', defaulting to 'balanced'")
        profile_name = "balanced"
    
    return SCALE_OUT_PROFILES[profile_name]


def validate_scale_out_config(config):
    """
    Validate scale-out configuration.
    
    Checks:
    - Total percentages sum to ~100%
    - R:R multipliers are ascending
    - All percentages are positive
    
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    if not config.get("enabled"):
        return True, "Scale-out disabled"
    
    levels = config.get("levels", [])
    if not levels:
        return False, "No levels defined"
    
    # Check percentages sum to ~100%
    total_pct = sum(level["close_pct"] for level in levels)
    if abs(total_pct - 1.0) > 0.01:  # Allow 1% tolerance
        return False, f"Percentages sum to {total_pct*100:.1f}%, expected 100%"
    
    # Check R:R multipliers are ascending
    r_mults = [level["r_mult"] for level in levels]
    if r_mults != sorted(r_mults):
        return False, "R:R multipliers must be in ascending order"
    
    # Check all percentages are positive
    if any(level["close_pct"] <= 0 for level in levels):
        return False, "All close percentages must be positive"
    
    return True, "Valid"


def print_scale_out_summary(profile_name="balanced"):
    """Print human-readable summary of scale-out profile."""
    config = get_scale_out_config(profile_name)
    
    print(f"\n{'='*60}")
    print(f"Scale-Out Profile: {profile_name.upper()}")
    print(f"{'='*60}")
    print(f"Description: {config.get('description', 'N/A')}")
    print(f"Enabled: {config.get('enabled', False)}")
    
    if config.get("enabled"):
        print(f"\nPartial Close Schedule:")
        cumulative = 0
        for i, level in enumerate(config["levels"], 1):
            cumulative += level["close_pct"]
            print(f"  Level {i}: Close {level['close_pct']*100:>5.1f}% @ {level['r_mult']:>4.1f}R  "
                  f"(Total closed: {cumulative*100:>5.1f}%)")
    print(f"{'='*60}\n")


# =============================================================================
# VALIDATION ON IMPORT
# =============================================================================
if __name__ == "__main__":
    # Validate all profiles on import
    print("Validating scale-out configurations...")
    for name, config in SCALE_OUT_PROFILES.items():
        valid, msg = validate_scale_out_config(config)
        status = "✅" if valid else "❌"
        print(f"{status} {name:15s}: {msg}")
    
    # Print example
    print_scale_out_summary("aggressive")
    print_scale_out_summary("conservative")
    print_scale_out_summary("balanced")
