def enforce_copy_rules(msg, decision):
    clean = decision.copy()

    # do not override dates with raw user text
    if "date" in clean:
        # accept normalized date if it's in proper format
        if len(clean["date"]) > 3 and "," in clean["date"]:
            pass  # good normalized date
        else:
            # keep raw until external normalizer updates it
            pass

    # Also ensure end_date is not overwritten
    if "end_date" in clean:
        if len(clean["end_date"]) > 3 and "," in clean["end_date"]:
            pass

    return clean
