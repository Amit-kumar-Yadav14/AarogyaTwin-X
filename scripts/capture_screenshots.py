import time
import os
from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = r"E:\health\screenshots"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

def capture_all():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Using a crisp 1920x1080 viewport with device_scale_factor=1.5 for ultra-sharp presentation images
        context = browser.new_context(
            viewport={"width": 1600, "height": 1000},
            device_scale_factor=1.5
        )
        page = context.new_page()

        print("Navigating to http://127.0.0.1:5173/ ...")
        page.goto("http://127.0.0.1:5173/")
        page.wait_for_selector(".patient-identity", timeout=15000)
        time.sleep(2)

        # ----------------------------------------------------
        # 1. Slide 6: Dashboard Overview
        # ----------------------------------------------------
        print("Capturing Slide 6: Dashboard Overview...")
        # Scroll to top
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(1)
        page.screenshot(
            path=os.path.join(SCREENSHOTS_DIR, "slide_06_dashboard_overview.png"),
            clip={"x": 240, "y": 60, "width": 1340, "height": 880}
        )

        # ----------------------------------------------------
        # 2. Slide 7: Forward Forecast & Conformal Band
        # ----------------------------------------------------
        print("Capturing Slide 7: Conformal Prediction Forecast...")
        forecast_el = page.query_selector("#forecast")
        if forecast_el:
            forecast_el.scroll_into_view_if_needed()
            time.sleep(1)
            forecast_el.screenshot(
                path=os.path.join(SCREENSHOTS_DIR, "slide_07_conformal_forecast.png")
            )

        # ----------------------------------------------------
        # 3. Slide 9: Clinician What-If Scenario Sandbox
        # Let's run this first while dropout is OFF!
        # ----------------------------------------------------
        print("Capturing Slide 9: Scenario Sandbox...")
        sandbox_el = page.query_selector("#sandbox")
        if sandbox_el:
            sandbox_el.scroll_into_view_if_needed()
            time.sleep(1)

            # Adjust Activity slider to 20 min
            page.fill("#scenario-activity", "20")
            page.dispatch_event("#scenario-activity", "change")

            # Adjust Carbs slider to 40 g
            page.fill("#scenario-carbs", "40")
            page.dispatch_event("#scenario-carbs", "change")
            time.sleep(1)

            # Click "Run comparison" button
            run_btn = page.query_selector(".scenario-actions button.button-primary")
            if run_btn:
                run_btn.click()
                print("Clicked Run comparison, waiting for response...")
                time.sleep(3)

            sandbox_el.scroll_into_view_if_needed()
            time.sleep(1)
            sandbox_el.screenshot(
                path=os.path.join(SCREENSHOTS_DIR, "slide_09_whatif_sandbox.png")
            )

        # ----------------------------------------------------
        # 4. Slide 8: The Game Changer - Intentional Abstention
        # Toggle "Simulate CGM dropout" ON
        # ----------------------------------------------------
        print("Capturing Slide 8: Intentional Abstention (Dropout ON)...")
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(1)

        # Click the label directly
        page.click("label.toggle-control")
        print("Toggled Simulate CGM dropout ON. Waiting for API update...")
        time.sleep(3)

        # Capture the overview showing the toggle is ON and the warning banner
        page.screenshot(
            path=os.path.join(SCREENSHOTS_DIR, "slide_08_abstention_controls_overview.png"),
            clip={"x": 240, "y": 60, "width": 1340, "height": 720}
        )

        # Now scroll down to the forecast panel to capture the empty state / "Prediction withheld"
        forecast_el = page.query_selector("#forecast")
        if forecast_el:
            forecast_el.scroll_into_view_if_needed()
            time.sleep(1)
            forecast_el.screenshot(
                path=os.path.join(SCREENSHOTS_DIR, "slide_08_intentional_abstention.png")
            )

        print("All screenshots successfully captured and saved in:", SCREENSHOTS_DIR)
        browser.close()

if __name__ == "__main__":
    capture_all()
