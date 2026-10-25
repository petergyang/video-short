# Persona review

A three-seat reaction pass on the draft, run before the user sees it. [eval.md](eval.md) audits the Short against rules. This catches what no rule can: an opening that is correct and still dull, one idea too many, a close that kills the rewatch.

Run it once the draft passes `qa.py` and `qa_plus.py`, before `review.py`. It costs no API calls beyond the agent.

## The three seats

| Seat | Watches as | Asks |
|---|---|---|
| The scroller | A phone thumb, sound off | Did the first second stop me, and on what? Does it still make sense muted? Is this one idea or three? |
| The topic viewer | Someone who came for this subject | What is wrong or oversimplified? What is missing that someone like me expects? What is the best thing here that got rushed? |
| The speaker | The user, from their own words | Does this sound like me? Is anything here something I already corrected? Is any fact, name or number wrong? |

Three seats, not four. The merge rule below turns on "two or more raised it", which only means something at a fixed panel size.

Give all three the same pack: the render at phone size, the same render muted, `work/qa/opening.jpg` and `contact.jpg`, and the clean transcript. The speaker seat also gets the user's notes from earlier rounds. Source that seat from what the user actually wrote, never from an impression of them. A seat running on a guess does not return no notes. It returns confident wrong ones, which is worse than an empty seat.

## Method

Run each seat in its own pass, and do not show it the others. Seats that read each other converge, and a converged panel makes the merge rule meaningless.

A seat reports what happened to the viewer and where. It does not propose the fix. Keeping those apart is what stops a reviewer from talking itself into the edit it already made.

## Merge

1. Fix anything two or more seats raise.
2. Fix every factual note, and every note in the speaker's voice, whatever the count.
3. A note that contradicts something the user already approved is reported as a conflict, not applied. The user decides those.
4. Report every note as done, can't, or won't, with the reason.
5. Re-run `qa.py` and `qa_plus.py`. Fixes break things: a trim moves a card, a recut moves a scene edge off its word.

The merge report is the deliverable. A note that appears in the pack and nowhere in the report is the failure this stage exists to prevent.
