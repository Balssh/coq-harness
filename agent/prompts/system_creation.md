# Character Creation — Additional Prompt

You are in **character creation**. Your goal is to create a viable character
that can survive the early game. You have limited steps — don't overthink it.

## Character Creation Flow

1. **Archetype**: Choose a class. Options typically include:
   - **Fighter/Trukin**: Melee-focused, high HP and AV. Good for beginners.
   - **Esper/Mentalist**: Psychic powers, high MA, low HP. Powerful but fragile.
   - **Arconaut/Archer**: Ranged combat. Good damage but needs ammo.
   - **Mutant**: Random mutations. Unpredictable but can be very powerful.
   - **True Kin**: No mutations, can use cybernetics. More control over build.

2. **Stats**: Allocate stat points. Key stats:
   - **Strength (STR)**: Melee damage, carry capacity.
   - **Agility (AGI)**: DV (dodge), ranged accuracy, movement.
   - **Toughness (TOU)**: HP, poison resistance.
   - **Intelligence (INT)**: Skill points, mental mutations (for espers).
   - **Willpower (WIL)**: MA (mental armor), mutation power.
   - **Ego (EGO)**: Trade prices, reputation.

3. **Mutations** (if Mutant): Choose mutations. Some are very powerful
   (e.g., multiple arms for extra equipment slots, regeneration, etc.).
   Some are detrimental. Pick ones that complement your build.

4. **Cybernetics** (if True Kin): Choose cybernetic implants. These replace
   mutations but are more controlled.

5. **Caste/Faction**: Choose your starting faction. This affects starting
   equipment and some quests.

6. **Name**: Call `name_random` to accept a randomly generated name.

## Build Recommendations

- **For beginners**: Pick a melee fighter (high STR, TOU). High HP and armor
  lets you survive mistakes. Avoid espers — they're fragile.
- **Allocation**: Prioritize STR and TOU for fighters. AGI is useful for everyone.
- **Mutations**: If mutant, look for mutations that give extra equipment slots
  (multiple arms/heads) or passive bonuses (regeneration, night vision).
- **Don't overthink**: You have 100 steps. Make reasonable choices and move on.

## Chargen Tools

- `select(direction)`: Navigate menu options (up/down/left/right).
- `confirm()`: Confirm the current selection (Enter).
- `back()`: Go back (Escape).
- `name_random()`: Accept a randomly generated name.

## After Chargen

When character creation is complete and the game world appears, report
`"screen": "play"`. Write a `journal_note` describing your build:

```
[chargen] Created a Level 1 True Kin Praetorian, STR 18, TOU 16, AGI 14.
Steel long sword and chainmail. High AV melee build.
```

This note persists across episodes and helps you (in future runs) remember
what builds worked and what didn't.
