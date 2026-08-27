# Targeted Remediation Gates - Adjudication

## Gate 1 - Planner stability: PASS
```json
{
 "scheduled": 20,
 "terminal": 20,
 "rows": [
  {
   "unit_id": "G1_F2_01",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F2_02",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F2_03",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F2_04",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F2_05",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F2_06",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F2_07",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F2_08",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F2_09",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F2_10",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F4_01",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F4_02",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F4_03",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F4_04",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F4_05",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F4_06",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F4_07",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F4_08",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  },
  {
   "unit_id": "G1_F4_09",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 2
  },
  {
   "unit_id": "G1_F4_10",
   "terminal_status": "success",
   "route": "relation",
   "relation": "held_by_target",
   "canonical": true,
   "plan_attempts": 1
  }
 ],
 "validated_canonical": 20,
 "behavior_route": 0,
 "gate": "PASS"
}
```

## Gate 2 - Blocker stability: FAIL
```json
{
 "gate": "FAIL",
 "checks": {
  "F2 001 TN": {
   "v": 5,
   "den": 5
  },
  "F2 001 no_false_assignment": {
   "v": 5,
   "den": 5
  },
  "F2 024 retained": {
   "v": 5,
   "den": 5
  },
  "F2 024 no_binding_conflict": {
   "v": 5,
   "den": 5
  },
  "F4 017 retained": {
   "v": 0,
   "den": 5
  },
  "challenge_001 no_false_assignment": {
   "v": 0,
   "den": 5
  },
  "challenge_004 elder_retained": {
   "v": 5,
   "den": 5
  },
  "challenge_004 no_child_false_assignment": {
   "v": 5,
   "den": 5
  },
  "challenge_003 no_false_assignment": {
   "v": 5,
   "den": 5
  },
  "challenge_003 ambiguity_safe": {
   "v": 5,
   "den": 5
  }
 },
 "case_breakdown": {
  "F2::fishing_001.jpeg": {
   "reps": [
    {
     "unit_id": "G2_F2__fishing_001_01",
     "status": "TN",
     "target_count": 0
    },
    {
     "unit_id": "G2_F2__fishing_001_02",
     "status": "TN",
     "target_count": 0
    },
    {
     "unit_id": "G2_F2__fishing_001_03",
     "status": "TN",
     "target_count": 0
    },
    {
     "unit_id": "G2_F2__fishing_001_04",
     "status": "TN",
     "target_count": 0
    },
    {
     "unit_id": "G2_F2__fishing_001_05",
     "status": "TN",
     "target_count": 0
    }
   ]
  },
  "F2::fishing_024.jpeg": {
   "reps": [
    {
     "unit_id": "G2_F2__fishing_024_01",
     "status": "retained",
     "target_count": 1
    },
    {
     "unit_id": "G2_F2__fishing_024_02",
     "status": "retained",
     "target_count": 1
    },
    {
     "unit_id": "G2_F2__fishing_024_03",
     "status": "retained",
     "target_count": 1
    },
    {
     "unit_id": "G2_F2__fishing_024_04",
     "status": "retained",
     "target_count": 1
    },
    {
     "unit_id": "G2_F2__fishing_024_05",
     "status": "retained",
     "target_count": 1
    }
   ]
  },
  "F4::fishing_017.jpeg": {
   "reps": [
    {
     "unit_id": "G2_F4__fishing_017_01",
     "status": "no_target",
     "target_count": 0
    },
    {
     "unit_id": "G2_F4__fishing_017_02",
     "status": "no_target",
     "target_count": 0
    },
    {
     "unit_id": "G2_F4__fishing_017_03",
     "status": "no_target",
     "target_count": 0
    },
    {
     "unit_id": "G2_F4__fishing_017_04",
     "status": "no_target",
     "target_count": 0
    },
    {
     "unit_id": "G2_F4__fishing_017_05",
     "status": "no_target",
     "target_count": 0
    }
   ]
  },
  "challenge_001": {
   "reps": [
    {
     "unit_id": "G2_challenge_001_01",
     "status": "false_assignment",
     "target_count": 2
    },
    {
     "unit_id": "G2_challenge_001_02",
     "status": "false_assignment",
     "target_count": 2
    },
    {
     "unit_id": "G2_challenge_001_03",
     "status": "false_assignment",
     "target_count": 2
    },
    {
     "unit_id": "G2_challenge_001_04",
     "status": "false_assignment",
     "target_count": 2
    },
    {
     "unit_id": "G2_challenge_001_05",
     "status": "false_assignment",
     "target_count": 2
    }
   ]
  },
  "challenge_004": {
   "reps": [
    {
     "unit_id": "G2_challenge_004_01",
     "status": "elder_retained",
     "target_count": 1
    },
    {
     "unit_id": "G2_challenge_004_02",
     "status": "elder_retained",
     "target_count": 1
    },
    {
     "unit_id": "G2_challenge_004_03",
     "status": "elder_retained",
     "target_count": 1
    },
    {
     "unit_id": "G2_challenge_004_04",
     "status": "elder_retained",
     "target_count": 1
    },
    {
     "unit_id": "G2_challenge_004_05",
     "status": "elder_retained",
     "target_count": 1
    }
   ]
  },
  "challenge_003": {
   "reps": [
    {
     "unit_id": "G2_challenge_003_04",
     "status": "retained_safe",
     "target_count": 1
    },
    {
     "unit_id": "G2_challenge_003_05",
     "status": "retained_safe",
     "target_count": 1
    },
    {
     "unit_id": "G2_challenge_003_01",
     "status": "retained_safe",
     "target_count": 1
    },
    {
     "unit_id": "G2_challenge_003_02",
     "status": "retained_safe",
     "target_count": 1
    },
    {
     "unit_id": "G2_challenge_003_03",
     "status": "retained_safe",
     "target_count": 1
    }
   ]
  }
 }
}
```

## Gate 3 - F2/F4 regression: FAIL
```json
{
 "gate": "FAIL",
 "system": {
  "scheduled": 60,
  "terminal": 60,
  "success": 60,
  "system_failure": 0,
  "provider_attempt_failure": 0,
  "unexpected_model": 0,
  "unexpected_endpoint": 0,
  "protocol_final_failure": 0,
  "validator_final_failure": 0
 },
 "summary": {
  "F2": {
   "positive_usable": "12/16",
   "positive_den": 16,
   "negative_tn": "12/12",
   "negative_den": 12,
   "frozen_invalid_kept": 2
  },
  "F4": {
   "positive_usable": "6/8",
   "positive_den": 8,
   "negative_tn": "18/19",
   "negative_den": 19,
   "frozen_invalid_kept": 3
  }
 },
 "new_invalid": [],
 "failures": []
}
```

## Gate 4 - Core relation controls: PASS
```json
{
 "gate": "PASS",
 "details": {
  "core_003": {
   "pass": true,
   "terminal_status": "success",
   "target_object": "person",
   "action": "outline",
   "target_count": 1,
   "expected": {
    "target_object": "person",
    "action": "outline",
    "target_count": 1
   }
  },
  "core_004": {
   "pass": true,
   "terminal_status": "success",
   "target_object": "person",
   "action": "cutout",
   "target_count": 1,
   "expected": {
    "target_object": "person",
    "action": "cutout",
    "target_count": 1
   }
  },
  "core_014": {
   "pass": true,
   "terminal_status": "success",
   "target_object": "person",
   "action": "outline",
   "target_count": 0,
   "expected": {
    "target_object": "person",
    "action": "outline",
    "target_count": 0
   }
  }
 }
}
```

