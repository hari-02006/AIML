import streamlit as st
import pandas as pd
import psycopg
import sys
import os

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Import dashboard query functions
from frontend.data.dashboard_queries import (
    get_date_range,
    get_overall_metrics,
    get_sales_trend,
    get_demand_vs_observed,
    get_top_products_units,
    get_lost_sales_by_product,
    get_stockout_overview,
    get_stockout_by_product,
    get_product_units_sold,
    get_category_units_sold,
    get_product_details,
    get_inventory_details,
    get_promotion_metrics,
    get_supplier_metrics,
    get_customer_metrics,
    get_current_stock_per_product,
    using_demo_data,
)
try:
    from utils.image_validator import validate_invoice_image, DOCUMENT_TYPES
    from utils.ocr_service import perform_ocr, get_available_engines, is_ocr_available, check_winocr_available, check_tesseract_available
    from utils.invoice_parser import parse_invoice_text
    from utils.paddleocr_vl_service import check_server_health, get_paddleocr_python_path
    from utils.product_matcher import match_product_against_catalog, validate_unit_conversion
    from utils.invoice_db import (
        get_product_catalog, get_available_categories, get_available_suppliers,
        get_product_inventory_status, check_duplicate_invoice,
        save_or_update_pending_invoice, create_new_product,
        approve_invoice_and_update_stock, reject_invoice, get_invoice_history
    )
except ImportError:
    from frontend.utils.image_validator import validate_invoice_image, DOCUMENT_TYPES
    from frontend.utils.ocr_service import perform_ocr, get_available_engines, is_ocr_available, check_winocr_available, check_tesseract_available
    from frontend.utils.invoice_parser import parse_invoice_text
    from frontend.utils.paddleocr_vl_service import check_server_health, get_paddleocr_python_path
    from frontend.utils.product_matcher import match_product_against_catalog, validate_unit_conversion
    from frontend.utils.invoice_db import (
        get_product_catalog, get_available_categories, get_available_suppliers,
        get_product_inventory_status, check_duplicate_invoice,
        save_or_update_pending_invoice, create_new_product,
        approve_invoice_and_update_stock, reject_invoice, get_invoice_history
    )

def main():
    st.set_page_config(page_title="SMART INVENTORY & DEMAND INTELLIGENCE", layout="wide")

    st.title("SMART INVENTORY & DEMAND INTELLIGENCE")
    st.subheader("Retail Analytics Dashboard")
    demo_mode = using_demo_data()
    if demo_mode:
        st.sidebar.info("Demo mode uses bundled sample data.")

    # Global Sidebar
    st.sidebar.title("Navigation")
    NAVIGATION_PAGES = [
        "Dashboard / Overview",
        "Sales Analytics",
        "Product Analytics",
        "Inventory Analytics",
        "Invoice Scanner"
    ]

    # Ensure safe fallback if an outdated page selection exists in session state
    if "nav_page" not in st.session_state or st.session_state["nav_page"] not in NAVIGATION_PAGES:
        st.session_state["nav_page"] = NAVIGATION_PAGES[0]

    page = st.sidebar.radio(
        "Go to",
        NAVIGATION_PAGES,
        key="nav_page"
    )

    if page != "Invoice Scanner":
        st.sidebar.markdown("---")
        st.sidebar.header("Global Filters")
        try:
            db_min_date, db_max_date = get_date_range()
        except (psycopg.Error, RuntimeError) as exc:
            st.error(f"Could not load sales data. Check the PostgreSQL setup in the README or start in demo mode. {exc}")
            st.stop()

        if pd.isnull(db_min_date) or pd.isnull(db_max_date):
            st.error("The sales table is empty. Load the sample data using the README setup instructions.")
            st.stop()

        start_date = st.sidebar.date_input("Start Date", db_min_date)
        end_date = st.sidebar.date_input("End Date", db_max_date)
        if start_date > end_date:
            st.error("Start Date must be on or before End Date.")
            st.stop()

    def format_currency(val):
        if pd.isna(val): return "₹0.00"
        return f"₹{val:,.2f}"

    def format_number(val):
        if pd.isna(val): return "0"
        return f"{val:,}"

    if page == "Dashboard / Overview":
        st.header("Overview Dashboard")

        try:
            metrics_df = get_overall_metrics(start_date, end_date)
            if not metrics_df.empty:
                metrics = metrics_df.iloc[0]
                # Display quantity‑focused KPIs (remove revenue‑related ones)
                col1, col2, col3, col4, col5, col6 = st.columns(6)
                col1.metric("Total Units Sold", format_number(metrics['total_units_sold']))
                col2.metric("Total Products", format_number(metrics['total_products']))
                col3.metric("Current Inventory", format_number(metrics['current_inventory']))
                col4.metric("Total Lost Sales", format_number(metrics['total_lost_sales']))
                col5.metric("Stockout Product‑Days", format_number(metrics['stockout_product_days']))
                # Average Daily Units Sold over the selected range
                avg_daily = 0
                try:
                    trend_df = get_sales_trend(start_date, end_date)
                    if not trend_df.empty:
                        avg_daily = trend_df['units_sold'].mean()
                except Exception:
                    pass
                col6.metric("Avg Daily Units Sold", format_number(int(avg_daily)))
        except Exception as e:
            st.error(f"Unable to connect to the Smart Inventory PostgreSQL database. {e}")

        st.markdown("---")

        # Units Sold Trend Chart
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.subheader("Units Sold Trend")
            trend_df = get_sales_trend(start_date, end_date)
            if not trend_df.empty:
                trend_df = trend_df.set_index('date')
                st.line_chart(trend_df['units_sold'])
            else:
                st.info("No sales data available for the selected filters.")
        # Stockout Overview Chart (product-level)
        with col_chart2:
            st.subheader("Stockout Overview (by Product)")
            # Retrieve top products by stockout days
            stockout_df = get_stockout_by_product(10, start_date, end_date)
            if not stockout_df.empty:
                stockout_df = stockout_df.set_index('product_name')
                st.bar_chart(stockout_df['stockout_days'])
            else:
                st.info("No stockout data available.")
        # Top Products by Units Sold and Lost Sales Charts
        col_chart3, col_chart4 = st.columns(2)
        with col_chart3:
            st.subheader("Top Products by Units Sold")
            top_units_df = get_top_products_units(10)
            if not top_units_df.empty:
                top_units_df = top_units_df.set_index('product_name')
                st.bar_chart(top_units_df['units_sold'])
        with col_chart4:
            st.subheader("Lost Sales by Product")
            lost_df = get_lost_sales_by_product(10, start_date, end_date)
            if not lost_df.empty:
                lost_df = lost_df.set_index('product_name')
                st.bar_chart(lost_df['lost_sales_units'])

        st.markdown("---")
        st.subheader("True Demand vs Observed Sales")
        dvo_df = get_demand_vs_observed(start_date, end_date)
        if not dvo_df.empty:
            dvo = dvo_df.iloc[0]
            col_d1, col_d2, col_d3, col_d4 = st.columns(4)
            col_d1.metric("Total True Demand", format_number(dvo['total_true_demand']))
            col_d2.metric("Total Observed Sales", format_number(dvo['total_observed_sales']))
            col_d3.metric("Total Lost Sales", format_number(dvo['total_lost_sales']))
            col_d4.metric("Lost Sales Rate", f"{float(dvo['lost_sales_rate']) * 100:.2f}%")

        st.markdown("---")
        st.header("KEY BUSINESS INSIGHTS")
        if not top_units_df.empty:
            st.markdown(f"- **{top_units_df.index[0]}** has the highest units sold.")
        if not dvo_df.empty:
            st.markdown(f"- **{format_number(dvo['total_lost_sales'])}** units of demand were not observed as sales because of inventory constraints.")

        so_overview_df = get_stockout_overview(start_date, end_date)
        if not so_overview_df.empty:
            so = so_overview_df.iloc[0]
            st.markdown(f"- **{format_number(so['total_stockout_days'])}** product-days experienced stockouts, affecting {format_number(so['products_with_stockouts'])} products.")

    elif page == "Sales Analytics":
        st.header("Sales Analytics")
        trend_df = get_sales_trend(start_date, end_date)
        if not trend_df.empty:
            # Daily Units Sold Trend
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Daily Units Sold Trend")
                df_units = trend_df.set_index('date')
                st.line_chart(df_units['units_sold'])
            # Product-wise Units Sold Bar Chart
            with col2:
                st.subheader("Top Products by Units Sold")
                prod_units_df = get_product_units_sold(limit=10, start_date=start_date, end_date=end_date)
                if not prod_units_df.empty:
                    prod_units_df = prod_units_df.set_index('product_name')
                    st.bar_chart(prod_units_df['units_sold'])
                else:
                    st.info("No product sales data available.")
            # Sales Data Table (date & units sold only)
            st.subheader("Sales Data Table")
            sales_table = trend_df[['date', 'units_sold']].copy()
            st.dataframe(sales_table)
            # Unit Sales Growth compared to previous period
            try:
                delta = end_date - start_date
                prev_start = start_date - delta - pd.Timedelta(days=1)
                prev_end = start_date - pd.Timedelta(days=1)
                prev_df = get_sales_trend(prev_start, prev_end)
                cur_units = trend_df['units_sold'].sum()
                prev_units = prev_df['units_sold'].sum() if not prev_df.empty else 0
                growth = (cur_units - prev_units) / prev_units if prev_units > 0 else 0
                st.metric("Unit Sales Growth", f"{growth*100:.2f}%")
            except Exception:
                st.info("Insufficient data for growth comparison.")
        else:
            st.info("No sales data found for this date range.")

    elif page == "Product Analytics":
        st.header("Product Analytics")
        cat_df = get_category_units_sold()
        categories = ['All'] + cat_df['category_name'].tolist() if not cat_df.empty else ['All']
        selected_cat = st.selectbox("Filter by Category", categories)

        prod_df = get_product_details(selected_cat)
        if not prod_df.empty:
            st.subheader("Product Performance")
            st.dataframe(prod_df)
        else:
            st.info("No data available for the selected category.")

    elif page == "Inventory Analytics":
        st.header("Inventory Analytics")

        # Current Live Stock per Product (Latest Recorded with Stale Reconciliation Status)
        st.subheader("Current Stock per Product")
        current_stock_df = get_current_stock_per_product(stale_days=30)
        if not current_stock_df.empty:
            # Style status column
            st.dataframe(
                current_stock_df[[
                    'product_id', 'product_name', 'category_name', 'current_stock',
                    'stock_unit', 'stock_status', 'latest_inventory_date', 'days_since_last_record'
                ]],
                use_container_width=True,
                column_config={
                    "product_id": "Product ID",
                    "product_name": "Product Name",
                    "category_name": "Category",
                    "current_stock": st.column_config.NumberColumn("Current Stock", format="%d"),
                    "stock_unit": "Stock Unit",
                    "stock_status": st.column_config.TextColumn("Status"),
                    "latest_inventory_date": st.column_config.DateColumn("Latest Recorded Date"),
                    "days_since_last_record": st.column_config.NumberColumn("Days Stale", format="%d"),
                }
            )
            st.caption("ℹ️ Note: Products flagged as *'Needs Reconciliation'* have not had recorded stock changes in over 30 days. Stock counts reflect last recorded closing stock until physical audit.")

        st.markdown("---")
        st.subheader("Historical Stockout & Demand Analysis")
        inv_df = get_inventory_details(start_date, end_date)
        if not inv_df.empty:
            st.dataframe(inv_df, use_container_width=True)

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Stockout Days by Product")
                st_df = inv_df[['product_name', 'total_stockout_days']].sort_values('total_stockout_days', ascending=False).head(10)
                st_df.set_index('product_name', inplace=True)
                st.bar_chart(st_df)
            with col2:
                st.subheader("Lost Sales by Product")
                ls_df = inv_df[['product_name', 'total_lost_sales']].sort_values('total_lost_sales', ascending=False).head(10)
                ls_df.set_index('product_name', inplace=True)
                st.bar_chart(ls_df)
        else:
            st.info("No historical inventory data found for selected date filters.")

    elif page == "Promotion Analytics":
        st.header("Promotion Analytics")
        promo_df = get_promotion_metrics()
        if not promo_df.empty:
            st.subheader("Promotion vs Non-Promotion Metrics")
            st.dataframe(promo_df)

            promo_df.set_index('promo_status', inplace=True)
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Revenue Comparison")
                st.bar_chart(promo_df['total_revenue'])
            with col2:
                st.subheader("Units Sold Comparison")
                st.bar_chart(promo_df['total_units_sold'])
        else:
            st.info("No promotion data available.")

    elif page == "Supplier Analytics":
        st.header("Supplier Analytics")
        sup_df = get_supplier_metrics()
        if not sup_df.empty:
            st.subheader("Supplier Performance")
            st.dataframe(sup_df)
        else:
            st.info("No supplier data available.")

    elif page == "Customer Analytics":
        st.header("Customer Analytics")
        cust_df = get_customer_metrics()
        if not cust_df.empty:
            st.subheader("Customer Segments")
            st.dataframe(cust_df)

            cust_df.set_index('customer_segment', inplace=True)
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Revenue by Segment")
                st.bar_chart(cust_df['total_revenue'])
            with col2:
                st.subheader("Orders by Segment")
                st.bar_chart(cust_df['num_orders'])
        else:
            st.info("No customer data available.")

    elif page == "Invoice Scanner":
        st.header("📄 Invoice Scanner")
        st.markdown(
            "Capture or upload retail and inventory invoice images directly from a mobile device "
            "or computer. Images will be staged for subsequent OCR and text extraction in Stage 8."
        )

        if demo_mode:
            st.info("Invoice upload and OCR preview are available in demo mode. Inventory intake and invoice history require PostgreSQL.")

        # 1. Document Type Selector
        st.subheader("1. Document Classification")
        selected_doc_type = st.selectbox(
            "Select Document Type",
            DOCUMENT_TYPES,
            help="Specify the classification of the invoice or document being captured."
        )

        # 2. Capture / Upload Method
        st.subheader("2. Capture or Upload Invoice Image")
        capture_mode = st.radio(
            "Capture Method",
            ["📁 Upload Existing Photograph", "📷 Device Camera Capture"],
            horizontal=True
        )

        raw_file = None
        if capture_mode == "📷 Device Camera Capture":
            st.caption("Point your mobile or computer camera directly at the invoice under good lighting.")
            raw_file = st.camera_input("Capture invoice photograph")
        else:
            st.caption("Upload an invoice document (PDF, TIFF, JPG, JPEG, or PNG format, up to 25 MB).")
            raw_file = st.file_uploader(
                "Upload invoice document",
                type=["jpg", "jpeg", "png", "pdf", "tiff", "tif"],
                help="Select an invoice or bill document (PDF, TIFF, or image) from your device."
            )

        # Discard / Replace option
        if st.session_state.get("scanned_invoice_image") is not None or raw_file is not None:
            if st.button("🗑️ Discard / Replace Image", key="discard_invoice_btn"):
                st.session_state.pop("scanned_invoice_image", None)
                st.session_state.pop("scanned_invoice_doc_type", None)
                st.session_state.pop("scanned_invoice_metadata", None)
                st.session_state.pop("scanned_invoice_filename", None)
                st.session_state.pop("scanned_invoice_ready", None)
                st.session_state.pop("invoice_ocr_result", None)
                st.session_state.pop("invoice_parsed_data", None)
                st.rerun()

        # Process and validate uploaded/captured file
        if raw_file is not None:
            file_bytes = raw_file.getvalue()
            file_name = getattr(raw_file, "name", "camera_capture.jpg")

            # Invalidate previous extraction session if a different file is selected or image content changed
            curr_stored_image = st.session_state.get("scanned_invoice_image")
            curr_stored_name = st.session_state.get("scanned_invoice_filename")
            if (curr_stored_name and curr_stored_name != file_name) or (curr_stored_image is not None and curr_stored_image != file_bytes):
                st.session_state.pop("invoice_ocr_result", None)
                st.session_state.pop("invoice_parsed_data", None)

            is_valid, validation_msg, metadata = validate_invoice_image(file_bytes, filename=file_name)

            if not is_valid:
                st.error(f"❌ Validation Error: {validation_msg}")
            else:
                st.session_state["scanned_invoice_image"] = file_bytes
                st.session_state["scanned_invoice_doc_type"] = selected_doc_type
                st.session_state["scanned_invoice_metadata"] = metadata
                st.session_state["scanned_invoice_filename"] = file_name

                st.success("Invoice document staged successfully and is ready for processing.")

                st.markdown("---")
                st.subheader("3. Image & Document Preview")

                preview_col1, preview_col2 = st.columns([3, 2])
                with preview_col1:
                    if metadata.get("format") == "PDF":
                        try:
                            import pypdfium2 as pdfium
                            pdf = pdfium.PdfDocument(file_bytes)
                            page_count = len(pdf)
                            selected_page = 1
                            if page_count > 1:
                                selected_page = st.selectbox(
                                    "Preview Page",
                                    range(1, page_count + 1),
                                    format_func=lambda p: f"Page {p} of {page_count}"
                                )
                            page_img = pdf[selected_page - 1].render(scale=1.5).to_pil().convert("RGB")
                            st.image(
                                page_img,
                                caption=f"Preview: {selected_doc_type} (Page {selected_page} of {page_count} • {metadata['size_kb']} KB)",
                                use_container_width=True
                            )
                        except Exception as e:
                            st.info(f"📄 PDF Document Uploaded ({metadata.get('page_count', 1)} pages, {metadata['size_kb']} KB).")
                    else:
                        st.image(
                            file_bytes,
                            caption=f"Preview: {selected_doc_type} ({metadata['format']} • {metadata['width']}x{metadata['height']} px • {metadata['size_kb']} KB)",
                            use_container_width=True
                        )
                with preview_col2:
                    st.markdown("### Document Metadata")
                    st.write(f"**Document Type:** {selected_doc_type}")
                    st.write(f"**Filename:** `{file_name}`")
                    st.write(f"**Format:** {metadata['format']}")
                    if metadata.get("page_count", 1) > 1:
                        st.write(f"**Pages:** {metadata['page_count']} pages")
                    else:
                        st.write(f"**Dimensions:** {metadata['width']} × {metadata['height']} pixels")
                    st.write(f"**File Size:** {metadata['size_kb']} KB")

                    st.markdown("---")
                    if st.button("✅ Confirm Document for Processing", type="primary", use_container_width=True):
                        st.session_state["scanned_invoice_ready"] = True
                        st.toast("Invoice document confirmed in session memory for OCR processing.")

                    if st.session_state.get("scanned_invoice_ready"):
                        st.info("📌 Status: Confirmed for Stage 8 OCR and data extraction pipeline.")

                # Section 4: OCR Extraction Pipeline
                st.markdown("---")
                st.subheader("4. Automatic Fast OCR & Inventory Extraction")

                win_avail, win_langs = check_winocr_available()
                tess_avail, _ = check_tesseract_available()
                if not win_avail and not tess_avail:
                    st.error("⚠️ No local OCR engine detected on this system. Windows Media OCR or Tesseract is required.")
                    can_extract = False
                else:
                    can_extract = True
                    target_lang = "en-US" if "en-US" in win_langs else (win_langs[0] if win_langs else "en")
                    st.caption(f"⚡ **Fast Automatic Engine:** Windows Media OCR ({target_lang}) • In-Memory SHA-256 Multi-Page Cache")

                # Extract Action Button
                col_ext1, col_ext2 = st.columns([2, 3])
                with col_ext1:
                    extract_clicked = st.button(
                        "📦 Extract Inventory Products",
                        type="primary",
                        use_container_width=True,
                        disabled=not can_extract,
                        help="Automatically run fast multi-page OCR to extract product names and purchased quantities across all pages."
                    )

                if extract_clicked and can_extract:
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    def update_progress(current_page: int, total_pages: int, message: str):
                        pct = int((current_page / max(total_pages, 1)) * 100)
                        progress_bar.progress(pct)
                        status_text.info(f"📄 {message}")

                    status_text.info("Initiating fast automatic OCR extraction...")
                    ocr_res = perform_ocr(
                        file_bytes,
                        preferred_engine="winocr",
                        filename=file_name,
                        progress_callback=update_progress
                    )
                    progress_bar.progress(100)
                    status_text.empty()

                    st.session_state["invoice_ocr_result"] = ocr_res
                    # Line items are already extracted across all pages with source_page
                    st.session_state["invoice_items"] = ocr_res.get("line_items", [])

                # Render extraction results if present
                ocr_result = st.session_state.get("invoice_ocr_result")
                items = st.session_state.get("invoice_items", [])

                if ocr_result is not None:
                    if not ocr_result.get("success"):
                        st.error(f"❌ OCR Extraction Failed: {ocr_result.get('error', 'Unknown error')}")
                    elif not ocr_result.get("raw_text", "").strip():
                        st.warning("⚠️ OCR completed, but no readable text was recognized in the document. Ensure the document is clear and readable.")
                    else:
                        word_cnt = ocr_result.get("word_count", 0)
                        line_cnt = ocr_result.get("line_count", 0)
                        page_cnt = ocr_result.get("page_count", 1)
                        st.success(f"✅ Invoice data extracted successfully using {ocr_result.get('engine')} ({word_cnt} words across {line_cnt} lines, {page_cnt} page{'s' if page_cnt > 1 else ''} recognized).")

                        proc_time = ocr_result.get("processing_time_sec", 0.0)
                        uncertain_items = [it for it in items if it.get("is_uncertain")]
                        uncertain_count = len(uncertain_items)

                        # Top Metrics: Total Pages, Recognized Products, Processing Time, Review Count
                        col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
                        col_m1.metric("Document Pages", page_cnt)
                        col_m2.metric("Products Recognized", len(items))
                        col_m3.metric("OCR Engine", ocr_result.get("engine", "Windows Media OCR"))
                        col_m4.metric("Processing Time", f"{proc_time:.2f}s" if proc_time > 0 else "< 1s")
                        col_m5.metric("Requires Review", uncertain_count)

                        if uncertain_count > 0:
                            st.warning(f"⚠️ {uncertain_count} product row(s) flagged for manual review due to missing or ambiguous product name/quantity.")

                        # Simplified & Editable Product & Quantity Table
                        st.markdown("### Extracted Inventory Items")
                        if items:
                            table_rows = []
                            for idx, it in enumerate(items, start=1):
                                p_name = it.get("product_name") or it.get("description") or f"Item {idx}"
                                q_val = it.get("quantity", 1.0)
                                q_fmt = int(q_val) if (isinstance(q_val, float) and q_val.is_integer()) else q_val
                                unit = it.get("unit") or ""
                                src_page = it.get("source_page", 1)
                                status = f"⚠️ {it.get('uncertain_reason')}" if it.get("is_uncertain") else "✅ Verified"

                                table_rows.append({
                                    "S. No.": idx,
                                    "Product Name": p_name,
                                    "Quantity": q_fmt,
                                    "Unit": unit,
                                    "Source Page": f"Page {src_page}",
                                    "Verification": status
                                })

                            df_display = pd.DataFrame(table_rows)
                            edited_df = st.data_editor(
                                df_display,
                                use_container_width=True,
                                num_rows="dynamic",
                                column_config={
                                    "S. No.": st.column_config.NumberColumn("S. No.", disabled=True),
                                    "Product Name": st.column_config.TextColumn("Product Name", required=True),
                                    "Quantity": st.column_config.NumberColumn("Quantity", min_value=0, required=True),
                                    "Unit": st.column_config.TextColumn("Unit"),
                                    "Source Page": st.column_config.TextColumn("Source Page", disabled=True),
                                    "Verification": st.column_config.TextColumn("Verification", disabled=True),
                                }
                            )
                            st.caption("💡 You can directly edit product names or quantities above before finalizing intake.")
                        else:
                            st.info("ℹ️ No product items could be recognized from the document. Inspect the raw text below.")

                        # Collapsible section for raw OCR inspection
                        with st.expander("🔍 Inspect Multi-Page OCR Raw Output & Diagnostics", expanded=False):
                            st.caption(f"Inspection: {ocr_result.get('word_count')} words across {ocr_result.get('line_count')} text lines from {ocr_result.get('engine')}.")
                            st.text_area("OCR Engine Output (All Pages)", value=ocr_result.get("raw_text", ""), height=220, disabled=True)
                            if ocr_result.get("pages"):
                                for p_info in ocr_result["pages"]:
                                    st.caption(f"**Page {p_info.get('page_num')}**: {p_info.get('word_count')} words, {len(p_info.get('line_items', []))} items extracted")

                        # =========================================================================
                        # SECTION 5: Shopkeeper Review, Product Matching & Approval (Stage 9)
                        # =========================================================================
                        if demo_mode:
                            st.stop()
                        st.markdown("---")
                        st.subheader("5. Product Reconciliation & Inventory Intake Approval")

                        try:
                            catalog = get_product_catalog()
                            categories = get_available_categories()
                            suppliers = get_available_suppliers()
                        except Exception as exc:
                            catalog = []
                            categories = []
                            suppliers = []
                            st.error(f"⚠️ Could not load database catalog: {str(exc)}")

                        # Duplicate Check Alert
                        doc_hash = ocr_result.get("doc_hash")
                        if not doc_hash and file_bytes:
                            import hashlib
                            doc_hash = hashlib.sha256(file_bytes).hexdigest()

                        dup_info = check_duplicate_invoice(doc_hash, invoice_reference=file_name)
                        if dup_info["is_exact_duplicate"]:
                            st.error(f"🚫 {dup_info['message']}")
                        elif dup_info["has_rescan_warning"]:
                            st.warning(f"⚠️ {dup_info['message']}")
                            confirm_separate = st.checkbox("Confirm: This is a separate, distinct physical delivery.", key="confirm_rescan")
                        else:
                            confirm_separate = True

                        # Match each extracted item against the catalog
                        reconciliation_rows = []
                        stale_alerts = []
                        unmatched_count = 0
                        unverified_count = 0

                        prod_options = ["-- Select Existing Product --", "➕ Create as New Product"] + [f"{p['product_id']}: {p['product_name']}" for p in catalog]

                        for idx, it in enumerate(items, start=1):
                            ocr_pname = it.get("product_name") or it.get("description") or ""
                            match_res = match_product_against_catalog(ocr_pname, catalog)
                            matched_prod = match_res.get("matched_product")

                            # Row Status
                            v_status = it.get("verification_status", "Needs Review")
                            if v_status != "Verified":
                                unverified_count += 1

                            matched_pid = matched_prod["product_id"] if matched_prod else None
                            matched_pname = matched_prod["product_name"] if matched_prod else None
                            canonical_unit = matched_prod.get("stock_unit") or "Units" if matched_prod else None

                            if not matched_prod:
                                unmatched_count += 1

                            # Check stale status if matched
                            if matched_pid:
                                stale_info = get_product_inventory_status(matched_pid)
                                if stale_info.get("requires_physical_confirmation"):
                                    stale_alerts.append({
                                        "product_id": matched_pid,
                                        "product_name": matched_pname,
                                        "latest_date": stale_info.get("latest_date"),
                                        "closing_stock": stale_info.get("latest_closing_stock"),
                                        "days_ago": stale_info.get("days_ago")
                                    })

                            reconciliation_rows.append({
                                "Line #": idx,
                                "Extracted Item": ocr_pname,
                                "Qty": it.get("quantity", 1.0),
                                "Extracted Unit": it.get("unit") or "",
                                "Matched Product": f"{matched_pid}: {matched_pname}" if matched_pid else "Unmatched",
                                "Canonical Unit": canonical_unit or "(Not Set)",
                                "Status": v_status
                            })

                        st.markdown("#### Item Matching & Verification Status")
                        df_recon = pd.DataFrame(reconciliation_rows)
                        st.dataframe(df_recon, use_container_width=True)

                        # Physical Stock Confirmation for Stale Products
                        confirmed_physical_openings = {}
                        if stale_alerts:
                            st.info("🕒 **Stale Inventory Reconciliation Required**: The following products have not had stock movements in over 30 days. Please verify the actual physical count currently in the store before adding this shipment:")
                            for sa in stale_alerts:
                                col_s1, col_s2 = st.columns([3, 2])
                                with col_s1:
                                    st.write(f"**{sa['product_id']}: {sa['product_name']}** — Last recorded: **{sa['closing_stock']} units** on {sa['latest_date']} ({sa['days_ago']} days ago)")
                                with col_s2:
                                    confirmed_val = st.number_input(
                                        f"Confirmed Physical Opening Stock for {sa['product_id']}",
                                        min_value=0,
                                        value=int(sa['closing_stock'] or 0),
                                        key=f"opening_stock_{sa['product_id']}"
                                    )
                                    confirmed_physical_openings[sa['product_id']] = confirmed_val

                        # Approval Gate & Actions
                        st.markdown("---")
                        col_btn1, col_btn2, col_btn3 = st.columns([2, 2, 3])

                        can_approve = (
                            not dup_info["is_exact_duplicate"]
                            and (confirm_separate if dup_info["has_rescan_warning"] else True)
                            and len(items) > 0
                        )

                        with col_btn1:
                            approve_clicked = st.button(
                                "✅ Approve Invoice & Update Stock",
                                type="primary",
                                disabled=not can_approve,
                                use_container_width=True,
                                help="Commit approved inventory quantities to PostgreSQL smart_inventory."
                            )

                        with col_btn2:
                            reject_clicked = st.button(
                                "❌ Reject Invoice",
                                type="secondary",
                                use_container_width=True,
                                help="Mark invoice as rejected and archive document without updating stock."
                            )

                        if approve_clicked:
                            # Prepare verified items payload
                            verified_payload = []
                            validation_failed = False

                            for idx, it in enumerate(items, start=1):
                                p_name = it.get("product_name") or it.get("description") or f"Item {idx}"
                                match_res = match_product_against_catalog(p_name, catalog)
                                matched_prod = match_res.get("matched_product")

                                if not matched_prod:
                                    st.error(f"❌ Cannot approve: Item #{idx} ('{p_name}') is unmatched.")
                                    validation_failed = True
                                    break

                                cq = it.get("quantity")
                                if cq is None or cq <= 0:
                                    st.error(f"❌ Cannot approve: Item #{idx} has invalid quantity ({cq}).")
                                    validation_failed = True
                                    break

                                verified_payload.append({
                                    "product_id": matched_prod["product_id"],
                                    "product_name": matched_prod["product_name"],
                                    "raw_line_text": p_name,
                                    "quantity": float(cq),
                                    "unit": it.get("unit") or matched_prod.get("stock_unit") or "Units",
                                    "canonical_quantity": float(cq),
                                    "conversion_factor": 1.0,
                                    "source_page": it.get("source_page", 1),
                                    "verification_status": "Verified"
                                })

                            if not validation_failed:
                                # Save pending draft if not already saved
                                draft_res = save_or_update_pending_invoice(
                                    file_bytes=file_bytes,
                                    original_filename=file_name,
                                    line_items=verified_payload,
                                    invoice_reference=file_name,
                                    invoice_date=None,
                                    total_pages=ocr_result.get("page_count", 1)
                                )

                                if draft_res["success"]:
                                    inv_id = draft_res["invoice_id"]
                                    ok, err = approve_invoice_and_update_stock(
                                        invoice_id=inv_id,
                                        verified_items=verified_payload,
                                        confirmed_physical_openings=confirmed_physical_openings
                                    )
                                    if ok:
                                        st.success(f"🎉 **Invoice #{inv_id} Approved Successfully!** Stock quantities updated in PostgreSQL smart_inventory.")
                                        st.balloons()
                                        st.session_state["invoice_approved"] = True
                                    else:
                                        st.error(f"❌ Approval Transaction Failed: {err}")
                                else:
                                    st.error(f"❌ Failed to persist invoice draft: {draft_res.get('error')}")

                        if reject_clicked:
                            draft_res = save_or_update_pending_invoice(
                                file_bytes=file_bytes,
                                original_filename=file_name,
                                line_items=items,
                                invoice_reference=file_name,
                                total_pages=ocr_result.get("page_count", 1)
                            )
                            if draft_res["success"]:
                                ok, err = reject_invoice(draft_res["invoice_id"])
                                if ok:
                                    st.warning(f"Invoice #{draft_res['invoice_id']} marked as REJECTED. Document archived without stock modifications.")
                                else:
                                    st.error(f"Rejection failed: {err}")

                # =========================================================================
                # SECTION 6: Approved Invoice History & Audit (Stage 9)
                # =========================================================================
                if demo_mode:
                    st.stop()
                st.markdown("---")
                st.subheader("6. Purchase Invoice Audit & History")
                try:
                    history_records = get_invoice_history(limit=20)
                    if history_records:
                        hist_df = pd.DataFrame(history_records)
                        st.dataframe(
                            hist_df[[
                                'id', 'invoice_reference', 'status', 'document_filename',
                                'item_count', 'total_units', 'created_at', 'approved_at'
                            ]],
                            use_container_width=True,
                            column_config={
                                "id": "Invoice ID",
                                "invoice_reference": "Reference",
                                "status": "Status",
                                "document_filename": "Filename",
                                "item_count": "Line Items",
                                "total_units": st.column_config.NumberColumn("Total Units", format="%.0f"),
                                "created_at": st.column_config.DatetimeColumn("Created At"),
                                "approved_at": st.column_config.DatetimeColumn("Approved At")
                            }
                        )
                    else:
                        st.info("No purchase invoices have been recorded in PostgreSQL yet.")
                except Exception as exc:
                    st.caption(f"Invoice history will populate once Stage 9 migration is applied to PostgreSQL.")

        # =========================================================================
        # PAGE: ML Feature Engineering (Stage 10)
        # =========================================================================
        elif page == "ML Feature Engineering":
            st.header("⚙️ Stage 10: ML Feature Engineering")
            st.markdown(
                "Transforms historical retail sales and daily inventory snapshots into a structured, "
                "product-level daily time-series dataset engineered for demand forecasting models (Stage 11). "
                "Enforces strict **zero-leakage** constraints and deterministic temporal precedence."
            )

            try:
                from ml.features import run_stage10_pipeline, load_latest_stage10_artifacts
            except ImportError:
                st.error("ML Feature Engineering module could not be loaded. Please ensure ml/features/ is present.")
                st.stop()

            # Action Toolbar
            col_act1, col_act2 = st.columns([2, 5])
            with col_act1:
                run_btn = st.button("🚀 Run / Regenerate Feature Pipeline", type="primary", use_container_width=True)

            if run_btn:
                with st.spinner("Extracting historical data from PostgreSQL & generating engineered features..."):
                    try:
                        success, feat_df, metrics, artifacts = run_stage10_pipeline()
                        st.success("✅ Feature pipeline completed successfully with zero target leakage!")
                        st.session_state["stage10_run_success"] = True
                    except Exception as exc:
                        st.error(f"❌ Feature pipeline failed: {exc}")

            # Load latest artifacts
            artifacts_data = load_latest_stage10_artifacts()

            if not artifacts_data.get("exists", False):
                st.info("ℹ️ No feature artifacts found on disk yet. Click **Run / Regenerate Feature Pipeline** above to process historical data.")
            else:
                meta = artifacts_data.get("metadata", {})
                metrics = meta.get("metrics", {})

                # KPI Summary Cards
                st.subheader("1. Pipeline Metrics & Scope")
                kpi_cols = st.columns(5)
                kpi_cols[0].metric("Total Rows", f"{metrics.get('total_output_rows', 0):,}")
                kpi_cols[1].metric("Feature Columns", f"{metrics.get('total_columns', 0)}")
                kpi_cols[2].metric("Products", f"{metrics.get('distinct_products', 0)}")
                kpi_cols[3].metric("Date Range", f"{metrics.get('min_sales_date', '')} to {metrics.get('max_sales_date', '')}")
                kpi_cols[4].metric("28d Ready Rows", f"{metrics.get('rows_with_sufficient_history_28d', 0):,}")

                # Data Integrity & Temporal Precautions
                st.markdown("---")
                st.subheader("2. Verified Data Integrity & Leakage Prevention")
                col_info1, col_info2 = st.columns(2)
                with col_info1:
                    st.markdown("**🛡️ Target Leakage Defenses:**")
                    st.markdown("""
                    - **Target Separation**: `demand_units` (actual daily quantity sold) is preserved strictly as the modeling target.
                    - **Shifted Rolling Windows**: All rolling stats (means, sums, stds) are computed on `demand_units.shift(1)` (closed='left'). Current day demand is never observed.
                    - **Group-Isolated Lags**: Time lags (`demand_lag_1`, `7`, `14`, `28`) strictly reset per product; zero cross-product bleed.
                    - **Historical Inventory Only**: Features reflect preceding day (T - 1) stock levels. Current day closing stock is strictly excluded.
                    """)
                with col_info2:
                    st.markdown("**⚠️ Historical Inventory Coverage Note:**")
                    st.warning(
                        "Historical inventory records span **2025-01-01 to 2026-01-07**. "
                        "Features for date T strictly use T - 1 inventory. "
                        "Gaps or non-covered dates carry `has_prev_day_inventory = False` rather than fabricated values."
                    )

                # Feature Dataset Preview
                st.markdown("---")
                st.subheader("3. Product-Level Feature Dataset Preview")
                preview_df = artifacts_data.get("preview_df", pd.DataFrame())
                st.dataframe(preview_df, use_container_width=True)

                # Downloads
                csv_path = artifacts_data.get("csv_path")
                parquet_path = artifacts_data.get("parquet_path")

                dl_col1, dl_col2 = st.columns(2)
                if csv_path and os.path.exists(csv_path):
                    with open(csv_path, "rb") as f:
                        dl_col1.download_button(
                            label="📥 Download Features Dataset (CSV)",
                            data=f,
                            file_name="daily_product_features.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
                if parquet_path and os.path.exists(parquet_path):
                    with open(parquet_path, "rb") as f:
                        dl_col2.download_button(
                            label="📥 Download Features Dataset (Parquet)",
                            data=f,
                            file_name="daily_product_features.parquet",
                            mime="application/octet-stream",
                            use_container_width=True
                        )

                # Feature Dictionary & Quality Summary Tabs
                st.markdown("---")
                st.subheader("4. Documentation & Quality Reports")
                tab_dict, tab_qual = st.tabs(["📋 Feature Data Dictionary", "🔍 Column Quality & Null Counts"])
                with tab_dict:
                    st.dataframe(artifacts_data.get("dictionary_df", pd.DataFrame()), use_container_width=True)
                with tab_qual:
                    st.dataframe(artifacts_data.get("quality_df", pd.DataFrame()), use_container_width=True)


if __name__ == "__main__":
    main()
