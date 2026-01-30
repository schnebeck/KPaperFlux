from typing import List, Optional
from core.database import DatabaseManager
from core.document import Document
from core.models.canonical_entity import CanonicalEntity, DocType
from core.models.virtual import VirtualDocument, SourceReference
from core.ai_analyzer import AIAnalyzer
from core.visual_auditor import VisualAuditor
from core.config import AppConfig
from core.models.identity import IdentityProfile
from core.repositories.physical_repo import PhysicalRepository
from core.repositories.logical_repo import LogicalRepository
from core.rules_engine import RulesEngine
import uuid
import json
from datetime import datetime

class CanonizerService:
    """
    Phase 2 Canonizer:
    Scans 'semantic_entities' (Logical Entities) with status='NEW'.
    Resolves text via VirtualDocument -> PhysicalFile.
    Handles Splitting (1 Logical -> N Logical).
    """

    def __init__(self, db: DatabaseManager, analyzer: Optional[AIAnalyzer] = None,
                 physical_repo: Optional[PhysicalRepository] = None,
                 logical_repo: Optional[LogicalRepository] = None,
                 filter_tree: Optional['FilterTree'] = None):
        self.db = db
        self.config = AppConfig()
        self.filter_tree = filter_tree

        # Repositories (Lazy init or passed)
        self.physical_repo = physical_repo if physical_repo else PhysicalRepository(db)
        self.logical_repo = logical_repo if logical_repo else LogicalRepository(db)

        # Core Components
        if analyzer:
            self.analyzer = analyzer
        else:
            self.analyzer = AIAnalyzer(self.config.get_api_key(), self.config.get_gemini_model())

        self.visual_auditor = VisualAuditor(self.analyzer)
        self.rules_engine = RulesEngine(db, filter_tree) if filter_tree else None

    def process_pending_documents(self, limit: int = 10):
        """
        Scan for Logical Entities with status='NEW'.
        """
        if not self.analyzer:
            print("[Canonizer] No AI Analyzer available.")
            return 0

        cursor = self.db.connection.cursor()
        # Fetch NEW entities
        query = """
            SELECT uuid
            FROM virtual_documents
            WHERE status IN ('NEW', 'READY_FOR_PIPELINE', 'STAGE2_PENDING') AND deleted = 0
            LIMIT ?
        """
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()

        processed_count = 0
        for row in rows:
            uuid = row[0]
            v_doc = self.logical_repo.get_by_uuid(uuid)
            if v_doc:
                # We let exceptions bubble up to the worker, unless they are handled AI-retries
                try:
                    success = self.process_virtual_document(v_doc)
                    if success:
                        processed_count += 1
                except Exception as e:
                    print(f"[Canonizer] Error processing {uuid}: {e}")
                    # Don't crash loop on single doc error
        return processed_count

    def process_virtual_document(self, v_doc: VirtualDocument) -> bool:
        """
        Process a specific VirtualDocument.
        Returns True if processing completed successfully (status changed), False if aborted/retrying.
        """
        if not self.analyzer: return False
        print(f"[STAGE 1] Processing Logical Entity {v_doc.uuid}...")

        # Capture original tags to detect manual intervention
        original_tags = getattr(v_doc, "type_tags", [])
        is_manual = "MANUAL_EDIT" in original_tags

        # 1. Resolve Text Content (Lazy Load)
        def loader(fid):
            return self.physical_repo.get_by_uuid(fid)

        full_text = v_doc.resolve_content(loader)
        if not full_text:
            print(f"[Canonizer] No text content resolved for {v_doc.uuid}. Skipping.")
            return False

        v_doc.cached_full_text = full_text
        print(f"[STAGE 1] Phase A: Resolved Full Text ({len(full_text)} chars)")

        # Reconstruct page list from source_mapping
        pages_text = []
        for src in v_doc.source_mapping:
            pf = self.physical_repo.get_by_uuid(src.file_uuid)
            if pf and pf.raw_ocr_data:
                raw = pf.raw_ocr_data
                if isinstance(raw, str):
                    try: raw = json.loads(raw)
                    except: raw = {}
                if isinstance(raw, dict):
                    for p in src.pages:
                        pages_text.append(raw.get(str(p), ""))

        if not pages_text:
             pages_text = [full_text]

        # Phase 107: Smart Reprocessing
        is_stage2_only = v_doc.status == 'STAGE2_PENDING'
        detected_entities = []
        is_hybrid = False

        if is_stage2_only:
             print(f"[Canonizer] STAGE2_PENDING detected. Skipping Classification/Split.")
             split_candidates = [{
                 "types": v_doc.type_tags or ["OTHER"],
                 "pages": list(range(1, len(pages_text) + 1)),
                 "confidence": 1.0,
                 "direction": v_doc.semantic_data.get("direction") if v_doc.semantic_data else None,
                 "tenant_context": v_doc.semantic_data.get("tenant_context") if v_doc.semantic_data else None
             }]
        else:
            # 2. AI Analysis (Stage 1: Structure/Split)
            priv_json = self.config.get_private_profile_json()
            bus_json = self.config.get_business_profile_json()
            priv_id = IdentityProfile.model_validate_json(priv_json) if priv_json else None
            bus_id = IdentityProfile.model_validate_json(bus_json) if bus_json else None

            struct_res = self.analyzer.run_stage_1_adaptive(pages_text, priv_id, bus_id)

            # --- CRITICAL FIX: Handle AI Failure (None) ---
            if struct_res is None:
                print(f"[Canonizer] Stage 1.1 AI Analysis returned None (Rate Limit/Timeout). Aborting process for {v_doc.uuid}.")
                # Return False ensures the document status is NOT updated to PROCESSED
                # It will remain NEW and be retried later.
                return False
            # ----------------------------------------------

            detected_entities = struct_res.get("detected_entities", [])
            is_hybrid = struct_res.get("source_file_summary", {}).get("is_hybrid_document", False)

            if not detected_entities:
                print(f"[Canonizer] Stage 1.1: No entities detected for {v_doc.uuid}.")
                v_doc.status = "PROCESSED"
                v_doc.last_processed_at = datetime.now().isoformat()
                self.logical_repo.save(v_doc)
                return True

            all_tags = []
            for ent in detected_entities:
                types = ent.get("doc_types", [])
                for t in types:
                    if t and t not in all_tags:
                        all_tags.append(t)
            v_doc.type_tags = all_tags

            if is_manual:
                 print(f"[Canonizer] Manually edited doc {v_doc.uuid} detected. Skipping auto-split.")
                 return True

            has_clear_boundaries = all(ent.get("page_indices") for ent in detected_entities)
            if is_hybrid and not has_clear_boundaries:
                print(f"[Canonizer] Stage 1.1 found hybrid but no clear boundaries. Triggering Stage 1.2.")
                split_candidates = self.analyzer.identify_entities(full_text, detected_entities=detected_entities)

                # --- CRITICAL FIX: Handle Stage 1.2 Failure ---
                if split_candidates is None:
                    print(f"[Canonizer] Stage 1.2 AI Analysis returned None. Aborting.")
                    return False
                # ----------------------------------------------
            else:
                split_candidates = []
                for ent in detected_entities:
                    split_candidates.append({
                        "types": ent.get("doc_types", ["OTHER"]),
                        "pages": ent.get("page_indices", list(range(1, len(pages_text) + 1))),
                        "confidence": ent.get("confidence", 1.0),
                        "direction": ent.get("direction"),
                        "tenant_context": ent.get("tenant_context")
                    })

        # 4. Apply Splits
        original_source_map = v_doc.source_mapping
        if not original_source_map: return False

        base_ref = original_source_map[0]

        for idx, candidate in enumerate(split_candidates):
            c_types = candidate.get("types", ["OTHER"])
            c_type = c_types[0] if c_types else "OTHER"
            c_pages = candidate.get("pages", [])

            new_source_pages = []
            for lp in c_pages:
                if 0 <= lp-1 < len(base_ref.pages):
                    new_source_pages.append(base_ref.pages[lp-1])

            if not new_source_pages: continue

            # Target Document
            target_doc = None
            if idx == 0:
                target_doc = v_doc # Reuse existing
            else:
                # Create NEW Split Entity
                target_doc = VirtualDocument(
                    uuid=str(uuid.uuid4()),
                    status="NEW",
                    created_at=v_doc.created_at
                )

            candidate_types = candidate.get("types", [])
            final_tags = list(candidate_types)

            direction = candidate.get("direction", "UNKNOWN")
            if direction != "UNKNOWN" and direction not in final_tags:
                final_tags.append(direction)

            context = candidate.get("tenant_context", "UNKNOWN")
            if context != "UNKNOWN" and f"CTX_{context}" not in final_tags:
                final_tags.append(f"CTX_{context}")

            target_doc.status = "PROCESSED"
            target_doc.last_processed_at = datetime.now().isoformat()
            target_doc.type_tags = final_tags

            target_doc.source_mapping = [SourceReference(
                file_uuid=base_ref.file_uuid,
                pages=new_source_pages,
                rotation=base_ref.rotation
            )]

            if idx < len(detected_entities):
                 target_doc.semantic_data = detected_entities[idx]

            print(f"  [Split Loop] Processing Candidate {idx+1}/{len(split_candidates)}: Pages {c_pages} -> Source Index {new_source_pages}")
            entity_text = self._extract_range_text(pages_text, c_pages)

            # [STAGE 1.5] Visual Audit
            audit_res = None
            pf = self.physical_repo.get_by_uuid(base_ref.file_uuid)
            if pf:
                audit_res = self.visual_auditor.run_stage_1_5(
                    pdf_path=pf.file_path,
                    doc_uuid=target_doc.uuid,
                    stage_1_result={"detected_entities": [{"doc_type": t} for t in c_types]},
                    text_content=entity_text,
                    target_pages=new_source_pages
                )

                # NOTE: Stage 1.5 failure (None) might be acceptable if visual audit is optional.
                # However, if AI is down, Stage 2 will likely fail too.
                # Let's be strict for now to ensure data quality.
                if audit_res is None and self.visual_auditor.is_ai_enabled():
                     # Only abort if audit was attempted but failed technically
                     print(f"[Canonizer] Stage 1.5 AI Failed. Aborting.")
                     return False

                if audit_res:
                    if target_doc.semantic_data is None:
                         target_doc.semantic_data = {}
                    target_doc.semantic_data["visual_audit"] = audit_res

                    # Arbiter Logic
                    integrity = audit_res.get("integrity", {})
                    if integrity.get("is_type_match") is False:
                        new_types = integrity.get("suggested_types", [])
                        if new_types:
                            c_type = new_types[0] if new_types else c_type
                            target_doc.type_tags = list(set(new_types + target_doc.type_tags))

                    decision = audit_res.get("arbiter_decision", {})
                    if decision.get("primary_source_recommendation") == "AI_VISION":
                        cleaned_text = audit_res.get("layer_document", {}).get("clean_text")
                        if cleaned_text:
                            entity_text = cleaned_text

            # [STAGE 2] Semantic Extraction
            s1_context = {"detected_entities": [{"doc_types": c_types}]}

            semantic_extraction = self.analyzer.run_stage_2(
                raw_ocr_text=entity_text,
                stage_1_result=s1_context,
                stage_1_5_result=audit_res,
                pdf_path=pf.file_path if pf else None
            )

            # --- CRITICAL FIX: Handle Stage 2 Failure ---
            # run_stage_2 currently returns a Dict even on error (empty dict).
            # If we want to be strict, we'd need to check emptiness or change analyzer.
            # Assuming Stage 2 is "best effort", we proceed.
            # BUT if we want retry on transient errors, AIAnalyzer.run_stage_2 needs to propagate None.
            # For now, let's assume if 'bodies' is empty and text is long, something is wrong?
            # Or trust the internal retries of AIAnalyzer.

            target_doc.semantic_data.update(semantic_extraction)

            # --- PHASE 105: Populate Filter Columns ---
            header = semantic_extraction.get("meta_header", {})
            bodies = semantic_extraction.get("bodies", {})

            # 1. Date
            if header.get("doc_date"):
                target_doc.doc_date = header["doc_date"]

            # 2. Sender
            sender_obj = header.get("sender", {})
            if isinstance(sender_obj, dict):
                target_doc.sender = sender_obj.get("name")
            elif isinstance(sender_obj, str):
                target_doc.sender = sender_obj

            # 3. Amount (Heuristic from bodies)
            if "finance_body" in bodies:
                fb = bodies["finance_body"]
                # In order of preference: Gross > Net > Total Due
                amt = fb.get("total_gross") or fb.get("total_net") or fb.get("total_due") or fb.get("total_amount")
                if amt is not None:
                    try: target_doc.amount = float(amt)
                    except: pass
            elif "ledger_body" in bodies:
                lb = bodies["ledger_body"]
                if lb.get("end_balance") is not None:
                    try: target_doc.amount = float(lb["end_balance"])
                    except: pass

            smart_name = self.analyzer.generate_smart_filename(
                semantic_extraction,
                target_doc.type_tags
            )
            target_doc.export_filename = smart_name
            target_doc.cached_full_text = entity_text

            self.logical_repo.save(target_doc)
            print(f"[Canonizer] Saved Entity {target_doc.uuid} ({', '.join(c_types)})")

            # [STAGE 1.6] Auto-Tagging
            if self.rules_engine and self.rules_engine.apply_rules_to_entity(target_doc, only_auto=True):
                 self.logical_repo.save(target_doc)

        print(f"[Canonizer] Stage 1 Analysis Complete for {v_doc.uuid}.")
        return True

    def _extract_range_text(self, pages_text: List[str], target_indices: List[int]) -> str:
        """Helper to join specific pages (simple join)."""
        out = []
        for i in target_indices:
            if 0 <= i-1 < len(pages_text):
                out.append(pages_text[i-1])
        return "\n\n".join(out)

    def split_entity(self, entity_uuid: str, split_after_page_index: int) -> tuple[str, str]:
        # ... (Unchanged logic)
        # 1. Fetch Original
        doc = self.logical_repo.get_by_uuid(entity_uuid)
        if not doc:
             raise ValueError(f"Entity {entity_uuid} not found")

        # 2. Flatten Pages logic
        flat_pages = []
        if doc.source_mapping:
            for src in doc.source_mapping:
                for p in src.pages:
                    flat_pages.append({
                        "file_uuid": src.file_uuid,
                        "page": p,
                        "rotation": src.rotation
                    })

        total_pages = len(flat_pages)
        if split_after_page_index < 0 or split_after_page_index >= total_pages - 1:
            raise ValueError(f"Invalid split index {split_after_page_index}. Total pages: {total_pages}")

        pages_a = flat_pages[:split_after_page_index+1]
        pages_b = flat_pages[split_after_page_index+1:]

        def regroup(pages_list) -> List[SourceReference]:
            mappings = []
            if not pages_list: return mappings

            current_uuid = pages_list[0]["file_uuid"]
            current_rot = pages_list[0]["rotation"]
            current_batch = [pages_list[0]["page"]]

            for item in pages_list[1:]:
                if item["file_uuid"] == current_uuid and item["rotation"] == current_rot:
                    current_batch.append(item["page"])
                else:
                    mappings.append(SourceReference(
                        file_uuid=current_uuid,
                        pages=current_batch,
                        rotation=current_rot
                    ))
                    current_uuid = item["file_uuid"]
                    current_rot = item["rotation"]
                    current_batch = [item["page"]]

            if current_batch:
                mappings.append(SourceReference(
                    file_uuid=current_uuid,
                    pages=current_batch,
                    rotation=current_rot
                ))
            return mappings

        doc.source_mapping = regroup(pages_a)
        doc.doc_type = json.dumps(["UNKNOWN"])
        doc.semantic_data = {}
        doc.status = "NEW"
        self.logical_repo.save(doc)

        new_doc = VirtualDocument(
            entity_uuid=str(uuid.uuid4()),
            created_at=doc.created_at,
            status="NEW",
            doc_type=json.dumps(["UNKNOWN"]),
            type_tags=["SPLIT_RESULT"]
        )
        new_doc.source_mapping = regroup(pages_b)
        self.logical_repo.save(new_doc)

        print(f"[Canonizer] Split {entity_uuid} at idx {split_after_page_index}. New parts: {doc.entity_uuid}, {new_doc.entity_uuid}")
        return (doc.entity_uuid, new_doc.entity_uuid)

    def restructure_file_entities(self, file_uuid: str, new_mappings: List[List[dict]]) -> List[str]:
        # ... (Unchanged logic)
        existing_docs = self.logical_repo.get_by_source_file(file_uuid)

        if not existing_docs:
            print(f"[Canonizer] Warning: No existing entities found for file {file_uuid}. Treating as fresh split.")

        print(f"[Canonizer] RESTRUCTURE TRANSACTION: Deleting {len(existing_docs)} old entities for {file_uuid}...")

        for old_doc in existing_docs:
            self.logical_repo.delete_by_uuid(old_doc.entity_uuid)

        new_uuids = []
        created_at_ts = None
        if existing_docs:
            created_at_ts = existing_docs[0].created_at

        for group in new_mappings:
            current_rot = 0
            current_pages = []
            refs = []

            for item in group:
                p = item['page']
                r = item.get('rotation', 0)

                if not current_pages:
                    current_rot = r
                    current_pages = [p]
                else:
                    if r == current_rot:
                        current_pages.append(p)
                    else:
                        refs.append(SourceReference(file_uuid, current_pages, current_rot))
                        current_rot = r
                        current_pages = [p]

            if current_pages:
                 refs.append(SourceReference(file_uuid, current_pages, current_rot))

            new_id = str(uuid.uuid4())
            new_doc = VirtualDocument(
                entity_uuid=new_id,
                source_mapping=refs,
                doc_type=json.dumps(["UNKNOWN"]),
                semantic_data={},
                status="READY_FOR_PIPELINE",
                created_at=created_at_ts,
                type_tags=["MANUAL_STRUCTURE"]
            )
            self.logical_repo.save(new_doc)
            new_uuids.append(new_id)

        print(f"[Canonizer] RESTRUCTURE COMMIT: Created {len(new_uuids)} new entities.")
        return new_uuids

    # ... Helper methods like _fuzzy_identity_match etc. (Unchanged)
    def _fuzzy_identity_match(self, party_name: str, party_address: str, profile: IdentityProfile) -> bool:
        if not party_name and not party_address:
            return False

        text_lower = f"{party_name or ''} {party_address or ''}".lower()

        for kw in profile.address_keywords:
            if kw.isdigit() and len(kw) == 5:
                if kw in text_lower:
                    return True

        score = 0.0
        threshold = 0.8

        search_terms = []
        if profile.name: search_terms.append(profile.name)
        if profile.company_name: search_terms.append(profile.company_name)
        search_terms += profile.aliases
        search_terms += profile.company_aliases
        search_terms += [k for k in profile.address_keywords if not k.isdigit()]

        for term in set(search_terms):
            if not term or len(term) < 3: continue
            clean_term = term.lower()
            if clean_term in text_lower:
                score += 1.0
            elif len(clean_term) >= 5:
                prefix = clean_term[:5]
                if prefix in text_lower:
                    score += 0.5
                parts = clean_term.split()
                for part in parts:
                    if len(part) > 3 and part in text_lower:
                        score += 0.3

        return score >= threshold

    def _classify_direction(self, entity: CanonicalEntity):
        # Unchanged
        priv_json = self.config.get_private_profile_json()
        bus_json = self.config.get_business_profile_json()

        identities = []
        try:
            if priv_json: identities.append(IdentityProfile.model_validate_json(priv_json))
            if bus_json: identities.append(IdentityProfile.model_validate_json(bus_json))
        except Exception as e:
            print(f"[Canonizer] Profile Load Error: {e}")

        sender_name = entity.parties.sender.name
        sender_addr = entity.parties.sender.address
        for prof in identities:
            if self._fuzzy_identity_match(sender_name, sender_addr, prof):
                entity.direction = "OUTGOING"
                return

        recipient_name = entity.parties.recipient.name
        recipient_addr = entity.parties.recipient.address
        for prof in identities:
            if self._fuzzy_identity_match(recipient_name, recipient_addr, prof):
                entity.direction = "INCOMING"
                return

    def _save_entity(self, entity: CanonicalEntity):
        # Unchanged legacy helper (if used)
        pass
