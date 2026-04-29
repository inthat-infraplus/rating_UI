# Task Detail QA Test Cases (Decision-First v1)

## 1) Scope
- In scope: `/tasks/{id}` task-detail review UX, related APIs, RBAC effects, export/csv/scale-profile/SAM integration, persistence and regressions.
- Out of scope: visual pixel-perfect checks on dashboard layout except interactions that block task-detail workflow.

## 2) Test Environment
- Server: local FastAPI app with SQLite and session middleware enabled.
- Browser: Chrome latest, Edge latest.
- Roles: `L1` reviewer/admin, `L2-A` assignee, `L2-B` non-assignee.
- Dataset A: 150+ images, mixed classes, linked `detailed_results.csv` with prediction boxes.
- Dataset B: 20 images, no CSV linked.
- Dataset C: malformed CSV and malformed scale profile for negative tests.
- Task states prepared: `draft`, `assigned`, `in_progress`, `submitted`, `in_qc`, `returned`, `approved`.

## 3) Coverage Matrix
- Decision-first actions: TC-DEC-001..012
- Keyboard-first interaction: TC-KBD-001..012
- Auto-advance/smart navigation: TC-AUTO-001..010
- Queue/object panel redesign: TC-UI-QUEUE-001..010, TC-UI-OBJ-001..010
- Quick review/theme/fatigue: TC-UX-001..010
- Batch accept: TC-BATCH-001..010
- Annotation/SAM flow: TC-ANN-001..014
- API contract/validation: TC-API-001..022
- RBAC/task lifecycle regression: TC-RBAC-001..018
- Export/correction integrity: TC-EXP-001..012
- Resilience/performance/concurrency: TC-NFR-001..010

## 4) Detailed Test Cases

## A) Decision-First Actions
| ID | Preconditions | Steps | Expected |
|---|---|---|---|
| TC-DEC-001 | Task loaded, image is `unreviewed` | Click `Accept (A)` | Decision becomes `correct`, review timestamp set, progress updates |
| TC-DEC-002 | Task loaded, image is `unreviewed` | Click `Fix (F)` | Decision becomes `wrong`, editing context shown, no forced image advance |
| TC-DEC-003 | Task loaded, selected prediction exists | Click `Delete (D)` | Selected prediction action becomes `delete`, annotations saved, smart-advance logic runs |
| TC-DEC-004 | Task loaded, no selected prediction and no predictions | Click `Delete (D)` | Error toast shown, no decision corruption |
| TC-DEC-005 | Image already `correct` | Click `Accept (A)` again | Idempotent behavior, no duplicate/incorrect counters |
| TC-DEC-006 | Image already `wrong` | Click `Fix (F)` again | Stays `wrong`, edit mode remains available |
| TC-DEC-007 | Image reviewed | Click `Reset (U)` | Decision returns `unreviewed`, review timestamp cleared |
| TC-DEC-008 | Image has polygons and prediction actions | `Reset (U)` then reload folder | Only decision resets; annotations/prediction actions persist as designed |
| TC-DEC-009 | Wrong image with 2+ predictions | Delete first object | Next unresolved object auto-selected before image navigation |
| TC-DEC-010 | Wrong image with all predictions deleted | Delete last unresolved object | Advances to next unresolved image |
| TC-DEC-011 | Auto-advance OFF | Accept/Fix/Delete actions | No automatic move to next image/object |
| TC-DEC-012 | Pending SAM preview exists | Trigger decision action | Confirm/cancel guard appears; cancel keeps current state |

## B) Keyboard Shortcuts
| ID | Preconditions | Steps | Expected |
|---|---|---|---|
| TC-KBD-001 | Task loaded | Press `A` | Same as Accept button |
| TC-KBD-002 | Task loaded | Press `F` | Same as Fix button |
| TC-KBD-003 | Prediction selected | Press `D` | Same as Delete action |
| TC-KBD-004 | Task loaded | Press `ArrowLeft` | Navigate previous item in active filter |
| TC-KBD-005 | Task loaded | Press `ArrowRight` | Navigate next item in active filter |
| TC-KBD-006 | Draw/SAM actions exist | Press `Z` | Undo action executed (`undo-polygon` / prompt undo path) |
| TC-KBD-007 | Task loaded | Press `C` | Alias of Accept still works |
| TC-KBD-008 | Task loaded | Press `W` | Alias of Fix still works |
| TC-KBD-009 | Task loaded | Press `U` | Reset to unreviewed works |
| TC-KBD-010 | Focus in input/textarea/select | Press `A/F/D/Z/C/W/U` | No review shortcut triggers |
| TC-KBD-011 | Draw mode active | Press nav/review shortcuts | Blocked while drawing as intended |
| TC-KBD-012 | SAM mode active | Press `z` then `x` | Prompt mode toggles Include/Exclude (no conflict with Undo expectation in SAM mode rules) |

## C) Auto-Advance and Navigation
| ID | Preconditions | Steps | Expected |
|---|---|---|---|
| TC-AUTO-001 | Filter = Unreviewed, multiple unreviewed images | Accept current image | Advances to next unreviewed in filter |
| TC-AUTO-002 | Current is last unreviewed in list | Accept current image | Wrap/next resolution follows `nextUnreviewedPath` behavior without crash |
| TC-AUTO-003 | Filter = Wrong | Accept image from wrong view | Queue and current selection remain consistent with new decision |
| TC-AUTO-004 | Fix action then draw polygon without save | Try navigation | Pending state handling follows guard behavior |
| TC-AUTO-005 | Fix action then save annotation | Confirm expected decision/view state | Image remains or advances per action path (no unintended jump before save) |
| TC-AUTO-006 | Delete in `redraw_all` mode | Delete selected object | Object-first advance disabled; image-level logic used |
| TC-AUTO-007 | Empty active filter | Try next/prev | Safe no-op, no JS errors |
| TC-AUTO-008 | Queue collapsed | Navigate via keys/buttons | Navigation still works, current item highlight updates |
| TC-AUTO-009 | Switch filter with current image excluded | Change filter | UI picks valid current item or fallback safely |
| TC-AUTO-010 | Persist UI state enabled | Navigate and reload page | Current image/filter restored correctly |

## D) Queue Panel
| ID | Preconditions | Steps | Expected |
|---|---|---|---|
| TC-UI-QUEUE-001 | Session loaded | Verify chips `Unreviewed/Wrong/Completed` | Only new chips shown; behavior correct |
| TC-UI-QUEUE-002 | Mixed decisions | Compare progress text | `X/Y completed` and `%` accurate |
| TC-UI-QUEUE-003 | Queue collapsed default | Open task | Queue starts collapsed as designed |
| TC-UI-QUEUE-004 | Queue expanded | Click collapse/expand | Layout updates without shifting canvas incorrectly |
| TC-UI-QUEUE-005 | Filter = Wrong | Ensure only `decision=wrong` shown | Count and list match backend session summary |
| TC-UI-QUEUE-006 | Filter = Completed | Ensure reviewed images only | `correct + wrong` reviewed items displayed |
| TC-UI-QUEUE-007 | Filter has no items | Open list | Shows empty-state text, no crash |
| TC-UI-QUEUE-008 | Large queue (150+) | Scroll and select item | Performance acceptable, active item sync correct |
| TC-UI-QUEUE-009 | Decision changed on active item | Observe queue badges | Status badges refresh instantly |
| TC-UI-QUEUE-010 | Reload folder | Check queue state | Filter/current path persisted from UI state |

## E) Object Panel
| ID | Preconditions | Steps | Expected |
|---|---|---|---|
| TC-UI-OBJ-001 | CSV linked with predictions | Open right panel | Rows show class/confidence/size/action |
| TC-UI-OBJ-002 | Hover row | Move mouse over object row | Corresponding overlay highlight increases |
| TC-UI-OBJ-003 | Click row | Click object row | Canvas zoom/select focuses object |
| TC-UI-OBJ-004 | Inline action keep | Click `Keep` | Prediction action persists after reload |
| TC-UI-OBJ-005 | Inline action replace | Click `Replace` | Action saved and visible in row state |
| TC-UI-OBJ-006 | Inline action delete | Click `Delete` | Action saved and reflected in export logic |
| TC-UI-OBJ-007 | Wrong image with no objects | Open object panel | Clear empty-state message |
| TC-UI-OBJ-008 | Prediction deleted then Undo polygon | Check action state | Undo does not silently revert prediction action unless explicitly designed |
| TC-UI-OBJ-009 | Quick review ON | Observe right panel | Edit-heavy right panel hidden/reduced |
| TC-UI-OBJ-010 | Switch images rapidly | Verify selected object reset | No stale object id causing wrong deletion |

## F) Quick Review, Theme, Fatigue UX
| ID | Preconditions | Steps | Expected |
|---|---|---|---|
| TC-UX-001 | Task loaded | Toggle `Quick Review` ON | Editing controls hidden, decision flow remains |
| TC-UX-002 | Quick Review ON | Try polygon tools | Disabled/hidden as intended |
| TC-UX-003 | Toggle theme from top-right nav button | Click theme button | Dark/light switches instantly |
| TC-UX-004 | Toggle theme from focus bar button | Click theme button | Both toggles stay in sync |
| TC-UX-005 | Theme changed | Reload page | Theme preference persists for session/page state |
| TC-UX-006 | Dark mode active | Verify text contrast on key UI texts | Readability passes (no low-contrast critical labels) |
| TC-UX-007 | Long session 2+ hours simulation | Repeated actions 500+ | No progressive UI lag/leak symptoms |
| TC-UX-008 | Mobile/narrow viewport | Open task detail | Controls usable; sticky decision bar remains accessible |
| TC-UX-009 | Desktop wide viewport | Measure workspace share | Canvas area remains primary focus (~70-80%) |
| TC-UX-010 | Toggle auto-advance | On/Off indicator | Button label and actual behavior match |

## G) Batch Accept
| ID | Preconditions | Steps | Expected |
|---|---|---|---|
| TC-BATCH-001 | Filter has candidates | Open modal | Preview count shown for default 0.85 |
| TC-BATCH-002 | Threshold changed to 0.95 | Observe preview | Candidate count updates live |
| TC-BATCH-003 | No candidates | Apply batch | Informational message, no API corruption |
| TC-BATCH-004 | Candidates exist | Confirm apply | `/api/review/batch` called once with expected paths |
| TC-BATCH-005 | Batch success | Verify summary | Reviewed/correct counters updated correctly |
| TC-BATCH-006 | Batch success in Wrong filter | Verify current view | List refresh consistent with filter semantics |
| TC-BATCH-007 | Modal close via X | Close modal | Modal hidden, errors cleared |
| TC-BATCH-008 | Click backdrop | Close modal | Same as cancel |
| TC-BATCH-009 | Inject invalid threshold (text/out of range) | Submit | Threshold clamped safely, no crash |
| TC-BATCH-010 | 150+ images performance | Run batch | Response and render time acceptable |

## H) Annotation and SAM
| ID | Preconditions | Steps | Expected |
|---|---|---|---|
| TC-ANN-001 | Wrong image, manual draw | Draw polygon and save | Polygon appears in mask list and persists |
| TC-ANN-002 | Polygon selected | Delete selected mask | Mask removed and persisted |
| TC-ANN-003 | Multiple polygons | Undo polygon action | Last draft/point removed as designed |
| TC-ANN-004 | SAM available | Enter SAM mode + add include point | Preview polygon appears |
| TC-ANN-005 | SAM preview exists | Confirm mask | Preview converted to committed polygon |
| TC-ANN-006 | SAM mode, add exclude points | Check preview update | Mask responds to include/exclude updates |
| TC-ANN-007 | SAM unavailable | Click SAM tool | Friendly unavailable reason shown |
| TC-ANN-008 | No prompts | Call segment | API returns 400 with clear message |
| TC-ANN-009 | Scale profile linked | Draw crack polygon | Value/unit auto-calculated in `m` |
| TC-ANN-010 | Scale profile linked | Draw area class polygon | Value/unit auto-calculated in `m^2` display path |
| TC-ANN-011 | No scale profile | Request metric | Graceful error, no app crash |
| TC-ANN-012 | correction_mode patch/redraw_all | Save annotations in each mode | Mode persisted and respected |
| TC-ANN-013 | prediction_actions keep/replace/delete | Save and reload | Actions persist and bind to object ids |
| TC-ANN-014 | `Fix` then annotation save | Check auto-advance expectation | No unintended immediate image advance before save |

## I) API Contract and Validation
| ID | Endpoint | Payload / Scenario | Expected |
|---|---|---|---|
| TC-API-001 | `POST /api/load-folder` | valid folder | 200 + session payload |
| TC-API-002 | `POST /api/load-folder` | missing folder | 404 |
| TC-API-003 | `POST /api/review` | valid decision | 200 + updated session |
| TC-API-004 | `POST /api/review` | invalid decision enum | 422 |
| TC-API-005 | `POST /api/review/batch` | valid list | 200 + batch update applied |
| TC-API-006 | `POST /api/review/batch` | empty `relative_paths` | 422/400 (validation) |
| TC-API-007 | `POST /api/ui-state` | `filter_mode=completed` | 200 and normalized state persisted |
| TC-API-008 | `POST /api/ui-state` | legacy `reviewed/selected` | accepted and normalized |
| TC-API-009 | `POST /api/annotations` | valid polygons/actions | 200 and summary updated |
| TC-API-010 | `POST /api/annotations` | malformed JSON body | 400 with parser detail |
| TC-API-011 | `POST /api/link-csv` | valid csv path | 200 and predictions populated |
| TC-API-012 | `POST /api/link-csv` | invalid path/not file | 400 |
| TC-API-013 | `POST /api/link-scale-profile` | valid profile | 200 |
| TC-API-014 | `POST /api/link-scale-profile` | no `in_roi=1` rows | 400 |
| TC-API-015 | `POST /api/calculate-area` | valid inputs | 200 + numeric value/unit |
| TC-API-016 | `POST /api/sam3/segment` | valid prompts | 200 + polygons |
| TC-API-017 | `POST /api/sam3/segment` | no point and no box | 400 |
| TC-API-018 | `POST /api/sam3/segment` | service unavailable | 503 |
| TC-API-019 | `GET /api/image` | valid relative path | 200 image bytes |
| TC-API-020 | `GET /api/image` | path traversal attempt | 404/400 blocked |
| TC-API-021 | `POST /api/export-updated-csv` | csv not linked | 400 |
| TC-API-022 | `POST /api/export` | target folder missing | 400 |

## J) RBAC and Task Lifecycle Regression
| ID | Preconditions | Steps | Expected |
|---|---|---|---|
| TC-RBAC-001 | Unauthenticated | Open `/tasks/{id}` | Redirect to login |
| TC-RBAC-002 | L2 assignee | Open task then start | Status flips `assigned/returned -> in_progress` |
| TC-RBAC-003 | L2 non-assignee | GET task detail API | 403 forbidden |
| TC-RBAC-004 | L2 assignee | Submit for QC | Allowed in `in_progress/assigned/returned` |
| TC-RBAC-005 | L2 assignee | Submit from invalid status | 409 invalid transition |
| TC-RBAC-006 | L1 | Approve in `submitted/in_qc` | Success |
| TC-RBAC-007 | L1 | Return without message | 400 validation error |
| TC-RBAC-008 | L1 | Return with message | Status -> `returned`, event logged |
| TC-RBAC-009 | L1 | Open QC on submitted | Status -> `in_qc` |
| TC-RBAC-010 | L1 | Create task with invalid L2 assignee | 400 |
| TC-RBAC-011 | L1 | Reassign in forbidden status | 409 |
| TC-RBAC-012 | L2 | Access `/api/users` | 403 |
| TC-RBAC-013 | L2 | Access `/api/admin/users` | 403 |
| TC-RBAC-014 | L1 self-edit | Demote self from L1 | 400 protected |
| TC-RBAC-015 | L1 self-edit | Deactivate self | 400 protected |
| TC-RBAC-016 | L1 | Reset another user password | 200 |
| TC-RBAC-017 | Task events thread | Add comment and list events | Comment appears with correct actor/time |
| TC-RBAC-018 | Soft delete task | Delete then list tasks | Task hidden from normal listing |

## K) Export and Data Integrity
| ID | Preconditions | Steps | Expected |
|---|---|---|---|
| TC-EXP-001 | Wrong-selected images exist + target path valid | Export ZIP | Zip contains `images/`, `annotated/`, `labels/`, `manifest.json`, `manifest.csv`, `classes.txt` |
| TC-EXP-002 | Selected images but target missing files | Export ZIP | 400 with missing-file preview message |
| TC-EXP-003 | Wrong-selected images exist | Export TXT | Filenames list matches selected images |
| TC-EXP-004 | No selected images | Export ZIP/TXT | 400 `No selected images to export` |
| TC-EXP-005 | CSV linked + corrections | Export updated CSV | Output includes polygon/action updates |
| TC-EXP-006 | prediction action `delete` | Export updated CSV | Deleted original prediction rows removed |
| TC-EXP-007 | prediction action `replace` with replace polygons | Export updated CSV | Original row replaced with correction rows |
| TC-EXP-008 | correction_mode `redraw_all` | Export updated CSV | Original rows dropped, redraw polygons used |
| TC-EXP-009 | class labels with mapping | Export labels | Class IDs match fixed mapping |
| TC-EXP-010 | unknown class in polygon | Export labels | Unknown class safely skipped |
| TC-EXP-011 | Unicode/UTF handling | Open CSV in Excel | UTF-8-sig readable, no corruption |
| TC-EXP-012 | Approved task + export flow | Perform export | Task can transition to/exported workflow without regression |

## L) Resilience, Error Handling, Performance
| ID | Preconditions | Steps | Expected |
|---|---|---|---|
| TC-NFR-001 | Corrupt state JSON with trailing garbage | Load folder | Store recovers (backup created, session still opens) |
| TC-NFR-002 | Force crash during save simulation | Trigger save | Atomic write prevents partial state file |
| TC-NFR-003 | Rapid decision spam (A/F/U) | 30 quick actions | No frontend freeze; final state deterministic |
| TC-NFR-004 | Rapid filter switching | Click chips repeatedly | No stale render exceptions |
| TC-NFR-005 | Large folder (1000 images) | Load and scroll queue | Acceptable load/scroll behavior |
| TC-NFR-006 | Large prediction count/image | Open object panel | UI still interactive |
| TC-NFR-007 | Network interruption during API call | Trigger action then offline | Error surfaced, no silent corruption |
| TC-NFR-008 | Parallel sessions same folder | Two browsers update same image | Last-write-wins behavior observed and documented |
| TC-NFR-009 | Browser refresh mid-annotation autosave | Refresh quickly | Last committed autosave state preserved; no invalid JSON |
| TC-NFR-010 | Long-run memory | 2-hour continuous review | No severe memory growth or input lag |

## 5) Suggested Execution Order
- Smoke pack (15 min): TC-DEC-001/002/003/007, TC-KBD-001/002/004/006, TC-AUTO-001, TC-BATCH-001/004, TC-API-003/005/009, TC-RBAC-002/004, TC-EXP-001.
- Core functional pack: all DEC/KBD/AUTO/QUEUE/OBJ/UX/BATCH/ANN.
- Regression pack before release: API + RBAC + EXP + NFR-001/002/003/007/008.
- Performance pack: NFR-005/006/010 plus BATCH-010.

## 6) Exit Criteria
- 0 critical/high defects open in DEC/KBD/AUTO/API/RBAC/EXP suites.
- All smoke pack cases pass on Chrome and Edge.
- No 400 errors from valid UI actions during 200-image run.
- No unreadable text issues in dark/light themes on task detail.
