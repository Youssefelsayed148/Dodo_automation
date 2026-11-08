<!-- prompt: consistency_check v1 -->
Compare a test scene with a character's approved sheet. The first image is the test scene; the remaining images are the character sheet (views and expressions).

Character: {character}

Check that in the test scene:
- face shape and proportions match the sheet
- the signature feature ({signature_feature}) is present and correct
- the line weight matches the sheet
- it is clearly the same character

Return {"pass": true|false, "issues": ["..."], "checks": {"face_shape": bool, "signature_feature": bool, "line_weight": bool}} where each check is true when it MATCHES.
