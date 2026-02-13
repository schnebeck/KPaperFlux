import os
import unittest
import pytest
import fitz
from pathlib import Path
from core.utils.hybrid_engine import HybridEngine

@pytest.mark.level2
class TestHybridMatchingAccuracy(unittest.TestCase):
    """
    Integration test to verify the matching accuracy of the HybridEngine
    using the complex demo invoices.
    """
    def setUp(self):
        self.engine = HybridEngine()
        self.base_dir = Path("/home/schnebeck/Dokumente/Projects/KPaperFlux/tests/resources/demo_invoices_complex")
        
        # Mapping: Scaled Scan File -> Original Native File
        self.expected_pairs = {
            "Demo_21_INVOICE_de.pdf": "Demo_01_INVOICE_de.pdf", # Clean
            "Demo_22_INVOICE_en.pdf": "Demo_02_INVOICE_en.pdf", # Clean
            "Demo_23_INVOICE_de.pdf": "Demo_03_INVOICE_de.pdf", # Stamp
            "Demo_24_INVOICE_en.pdf": "Demo_04_INVOICE_en.pdf", # Stamp
            "Demo_25_INVOICE_de.pdf": "Demo_05_INVOICE_de.pdf", # Outbound
            "Demo_29_INVOICE_de.pdf": "Demo_26_INVOICE_de.pdf"  # Telekom Challenge (Scan 29 is actually from Native 26)
        }

    def test_matching_accuracy(self):
        print("\n" + "="*80)
        print(f"{'SCAN FILE':<30} | {'BEST MATCH':<30} | {'SCORE':<10} | {'RESULT'}")
        print("-" * 80)
        
        all_pdfs = sorted(list(self.base_dir.glob("*.pdf")))
        # Natives: Demo_01 to Demo_20 + Telekom Test (Demo_26-28). MUST EXCLUDE sim_ files.
        natives = [f for f in all_pdfs if f.name.startswith("Demo_") and not f.name.startswith("sim_") and int(f.name.split("_")[1]) in list(range(1, 21)) + [26, 27, 28]]
        # Scans: Demo_21-25 and Challenge Scan 29
        scans = [f for f in all_pdfs if f.name.startswith("Demo_") and int(f.name.split("_")[1]) in [21, 22, 23, 24, 25, 29]]
        # Safety check: if natives are not found, search in all_pdfs
        if not natives:
             natives = [f for f in all_pdfs if "Demo_" in f.name and not "sim_" in f.name]
        
        import time
        start_time = time.time()
        
        # Pre-render cache simulation (100 and 150)
        cache_100 = {}
        features_100 = {}
        cache_150 = {}
        features_150 = {}
        
        print("[SETUP] Precomputing native features...")
        for n in natives:
            doc = fitz.open(n)
            img_100 = self.engine.pdf_page_to_numpy(doc, 0, dpi=100)
            cache_100[n] = img_100
            features_100[n] = self.engine.get_orb_features(img_100)
            
            img_150 = self.engine.pdf_page_to_numpy(doc, 0, dpi=150)
            cache_150[n] = img_150
            features_150[n] = self.engine.get_orb_features(img_150)
            doc.close()
            
        available_natives = list(natives)
        success_count = 0
        GREEDY_LIMIT_100 = 250
        REFINEMENT_COUNT = 3
        
        for scan in sorted(scans, key=lambda x: x.name):
            doc_s = fitz.open(scan)
            scan_img_100 = self.engine.pdf_page_to_numpy(doc_s, 0, dpi=100)
            scan_img_150 = self.engine.pdf_page_to_numpy(doc_s, 0, dpi=150)
            doc_s.close()
            
            # Precompute scan features ONCE
            kp_s_100, des_s_100 = self.engine.get_orb_features(scan_img_100)
            kp_s_150, des_s_150 = self.engine.get_orb_features(scan_img_150)
            
            # STAGE 1 (100 DPI)
            candidates = []
            for native in available_natives:
                kp_n, des_n = features_100[native]
                score = self.engine.calculate_pair_score(
                    str(scan), str(native), 
                    native_img_cached=cache_100[native],
                    scan_img_cached=scan_img_100,
                    kp_native_cached=kp_n,
                    des_native_cached=des_n,
                    kp_scan_cached=kp_s_100,
                    des_scan_cached=des_s_100,
                    dpi=100
                )
                candidates.append((native, score))
            
            candidates.sort(key=lambda x: x[1])
            best_native, best_score = candidates[0]
            
            # STAGE 2 (150 DPI Refinement)
            needs_refinement = True
            if best_score < 100:
                if len(candidates) > 1 and candidates[1][1] > best_score * 5:
                    needs_refinement = False

            if needs_refinement:
                print(f"[DEBUG] Scan {scan.name}: Triggering 150 DPI Refinement (Stage 1 Best: {int(best_score)})")
                final_candidates = []
                for native, _ in candidates[:REFINEMENT_COUNT]:
                    kp_n, des_n = features_150[native]
                    
                    p_score = self.engine.calculate_pair_score(
                        str(scan), str(native),
                        native_img_cached=cache_150[native],
                        scan_img_cached=scan_img_150,
                        kp_native_cached=kp_n,
                        des_native_cached=des_n,
                        kp_scan_cached=kp_s_150,
                        des_scan_cached=des_s_150,
                        dpi=150
                    )
                    final_candidates.append((native, p_score))
                final_candidates.sort(key=lambda x: x[1])
                
                # Debug top candidates
                for i, (cand, cand_score) in enumerate(final_candidates[:3]):
                    print(f"  [Top {i+1}] {cand.name}: {cand_score:.4f}")

                best_native, best_score = final_candidates[0]
                print(f"[DEBUG] -> Stage 2 Final: {best_native.name} with Score {best_score:.4f}")
            else:
                print(f"[DEBUG] Scan {scan.name}: Finalized at 100 DPI (Confident Match, Score: {int(best_score)})")
            
            expected = self.expected_pairs.get(scan.name)
            match_name = best_native.name if best_native else "NONE"
            result_str = "SUCCESS" if match_name == expected else "FAILURE"
            
            if result_str == "SUCCESS": 
                success_count += 1
                if best_score < GREEDY_LIMIT_100:
                    available_natives.remove(best_native)
                    print(f"POOLED OUT: {match_name}")
            
            print(f"{scan.name:<30} | {match_name:<30} | {int(best_score):<10} | {result_str}")

        end_time = time.time()
        print("="*80)
        print(f"Total Accuracy: {success_count}/{len(scans)} ({(success_count/len(scans)*100):.1f}%)")
        print(f"Total Match Time: {end_time - start_time:.2f} seconds")
        print("="*80)
        
        self.assertEqual(success_count, len(scans), f"Matching accuracy {success_count}/{len(scans)} below 100%.")

if __name__ == "__main__":
    unittest.main()
