# GC9A01 Display Driver for MicroPython/Python (with PinPong and Pillow)

This library provides a Python class to control GC9A01-based 240x240 round TFT LCDs, primarily designed for use with MicroPython boards like the Unihiker, utilizing the PinPong library for GPIO/SPI communication and the Pillow (PIL) library for graphics rendering.

A key feature of this version is the inclusion of a **software framebuffer**. This allows for more advanced graphics operations, such as correct alpha blending of semi-transparent images, by maintaining an in-memory representation of the display's content.

## Features

* Initialization and control of GC9A01 displays.
* Drawing primitives: pixels, lines, rectangles (filled/outline), circles (filled/outline).
* Text rendering with TrueType fonts.
* Displaying Pillow (PIL) Image objects.
* Software framebuffer for advanced 2D graphics operations.
* Alpha blending of RGBA images against the current framebuffer content.
* Backlight control.

## Dependencies

1.  **PinPong Library:** For hardware interaction (GPIO, SPI). This is typically pre-installed on Unihiker.
    * Installation: `pip install pinpong` (if not already present).
2.  **Pillow (PIL) Library:** For all image manipulation, drawing, and text rendering.
    * Installation: `pip install Pillow`

## Setup

1.  **Library File:** Place the `GC9A01.py`  file on your device (e.g., Unihiker) in a directory where your main script can import it, or install it as a custom library.
2.  **Dependencies:** Ensure PinPong and Pillow are installed in your Python environment.
3.  **Font File:** For text rendering, you'll need a TrueType font file (e.g., `DejaVuSans-Bold.ttf`) accessible by your script.

## Class: `GC9A01`

### Constructor

`__init__(self, spi_bus, dc_pin_obj, rst_pin_obj, cs_pin_obj=None, bl_pin_obj=None, width=240, height=240, madctl_val=0x08)`

* `spi_bus`: An initialized PinPong `SPI` object for communication with the display.
* `dc_pin_obj`: A PinPong `Pin` object configured as an output for the Data/Command (DC or RS) line.
* `rst_pin_obj`: A PinPong `Pin` object configured as an output for the Reset (RST) line.
* `cs_pin_obj` (optional): A PinPong `Pin` object for Chip Select (CS). If `None` (default), it's assumed the CS line is handled by the SPI peripheral (e.g., when `cs` is specified during `SPI` object creation in PinPong) or not manually controlled by this class. If provided, this class will manage toggling it.
* `bl_pin_obj` (optional): A PinPong `Pin` object configured as an output for the backlight control.
* `width` (optional): Width of the display in pixels (default: 240).
* `height` (optional): Height of the display in pixels (default: 240).
* `madctl_val` (optional): The value for the Memory Access Control (MADCTL) register (0x36), controlling screen orientation and color order (default: 0x08).

Upon initialization, if Pillow is available, a software framebuffer (`self.framebuffer`) is created as an RGB image representing the display. All subsequent drawing operations will update this framebuffer, and then the relevant portion is sent to the physical display.

### Core Display Control Methods

* **`init_display()`**
    Initializes the GC9A01 controller with a standard sequence of commands. Also initializes the software framebuffer to black.
* **`reset()`**
    Performs a hardware reset of the display using the RST pin.
* **`display_on()` / `display_off()`**
    Turns the display panel output on or off.
* **`backlight_on()` / `backlight_off()`**
    Controls the display's backlight if `bl_pin_obj` was provided.
* **`set_window(x_start, y_start, x_end, y_end)`**
    Sets the active drawing window (column and row addresses) on the physical display hardware for subsequent RAM write operations. Coordinates are clipped to display boundaries.
* **`write_ram_prepare()`**
    Sends the Memory Write (RAMWR) command to the display, preparing it to receive pixel data.

### Software Framebuffer and Compositing

The library maintains `self.framebuffer` (a Pillow `Image` object) and `self.fb_draw` (a Pillow `ImageDraw` object for drawing on the framebuffer).

* **`draw_image_rgb(self, x, y, pil_image_rgb)`**
    Draws an opaque Pillow `Image` (expected to be in "RGB" mode) onto the software framebuffer at `(x,y)` and then updates the corresponding region on the physical display.
* **`draw_image_rgba_composited(self, x, y, pil_image_rgba)`**
    This is the primary method for drawing images with transparency.
    1.  Takes a Pillow `Image` in "RGBA" mode.
    2.  Crops the relevant background area from the current software framebuffer.
    3.  Alpha-composites the provided RGBA image onto this cropped background region.
    4.  Updates the software framebuffer with the composited result.
    5.  Sends the updated region to the physical display.
    This allows semi-transparent images to correctly blend with the existing content of the screen (as mirrored in the software framebuffer).

### Standard Drawing Methods

These methods draw onto the software framebuffer first, and then the affected region of the framebuffer is sent to the physical display. This ensures that anti-aliasing performed by Pillow is done against the actual content of the framebuffer.

* **`pixel(x, y, color_rgb565)`**
    Draws a single pixel at `(x,y)` with the given RGB565 color.
* **`line(x0, y0, x1, y1, color_rgb565, line_width=1)`**
    Draws a line from `(x0,y0)` to `(x1,y1)`. Pillow's anti-aliasing will blend the line's edges with the content of the software framebuffer.
* **`rectangle(x, y, width, height, outline_rgb565=None, fill_rgb565=None, outline_width=1)`**
    Draws a rectangle. Can be filled, outlined, or both.
* **`fill_rect(x, y, width, height, color_rgb565)`**
    A convenience method to draw a filled rectangle.
* **`fill_screen(color_rgb565)`**
    Fills the entire software framebuffer and physical display with the specified RGB565 color.
* **`circle(x_center, y_center, radius, outline_rgb565=None, fill_rgb565=None, outline_width=1)`**
    Draws a circle. Can be filled, outlined, or both.
* **`text(x, y, text_string, font_path, font_size, text_color_rgb888, background_color_rgb888=None)`**
    Renders text using a TrueType font.
    * `text_color_rgb888`: Text color as an (R,G,B) tuple.
    * `background_color_rgb888` (optional): If provided, the text area will be filled with this color before drawing the text. If `None`, the text is drawn directly onto the existing content of the software framebuffer.

### Low-Level Hardware Drawing (Use with Caution)

* **`draw_image_rgb565(x, y, width, height, image_buffer_bytes)`**
    Writes a raw buffer of RGB565 pixel data directly to the physical display hardware.
    **Important:** This method *does not* update the software framebuffer. Using it can cause the software framebuffer to become out of sync with the physical display, potentially leading to incorrect results for subsequent alpha-blending operations. It's intended for optimized scenarios where direct hardware writes are needed and the software framebuffer state is managed externally or not relevant.

### Internal Helper Methods

The library contains several internal helper methods (usually prefixed with an underscore) for color conversion, SPI communication, and managing the software framebuffer updates. Key among them:

* **`_pil_image_to_rgb565_bytearray(self, pil_image)`:** Converts a Pillow image to the RGB565 byte format required by the display. **Crucially, if a Pillow image in "RGBA" mode is passed directly to this method, it will be flattened against a black background.** Higher-level functions in this library are designed to pass pre-composited "RGB" images to it to avoid this issue when transparency is intended.
* **`_update_framebuffer_region(self, x, y, width, height)`:** Takes a region from the software framebuffer, converts it, and sends it to the physical display.

## Example Usage (`if __name__ == "__main__":`)

The `if __name__ == "__main__":` block in the library file provides a demonstration of its capabilities:

1.  **Initialization:**
    * Sets up the necessary GPIO pins (CS, DC, RST, BL) using PinPong.
    * Initializes the SPI bus.
    * Creates an instance of the `GC9A01` class.
    * Calls `display.init_display()` to initialize the hardware and the software framebuffer.

2.  **Filling the Screen:**
    * `display.fill_screen(screen_bg_color_565)`: Fills the entire display (both software framebuffer and hardware) with a dark teal color.

3.  **Drawing Opaque Shapes:**
    * `display.fill_rect(...)`: Draws an opaque red rectangle.
    * `display.line(...)`: Draws an opaque white line.
    * These operations are rendered onto the software framebuffer, and then the affected regions are pushed to the display.

4.  **Drawing Semi-Transparent RGBA Images with Alpha Compositing:**
    * **Green Circle:**
        * A Pillow `Image` is created in "RGBA" mode (`circle_img_rgba`). A semi-transparent green circle (alpha=128) with a semi-transparent yellow outline is drawn onto this image. The background of `circle_img_rgba` itself is fully transparent.
        * `display.draw_image_rgba_composited(70, 40, circle_img_rgba)`: This method is called.
            * It internally crops the region `(70, 40)` to `(70+100, 40+100)` from the software framebuffer (which currently contains the blue background and parts of the red rectangle/white line).
            * It alpha-composites the `circle_img_rgba` onto this cropped background.
            * The resulting blended image is pasted back into the software framebuffer at `(70,40)`.
            * This updated region is then sent to the physical display.
            * The result is the green circle appearing correctly blended with whatever was behind it on the screen.
    * **Magenta Rectangle with Text:**
        * A similar process is followed for a semi-transparent magenta rectangle with opaque white text on it. It's drawn using `draw_image_rgba_composited` and correctly blends with the previously drawn elements.

5.  **Drawing Text with an Opaque Background:**
    * `display.text(...)` is called with a `background_color_rgb888` specified.
    * This draws yellow text on a gray background. The `text` method handles drawing this opaque block onto the software framebuffer and then updating the hardware.

This example showcases how to use both standard opaque drawing methods and the more advanced `draw_image_rgba_composited` for achieving transparency effects by leveraging the software framebuffer.

## Notes on Transparency and Performance

* The GC9A01A display controller itself does not provide a hardware command to read from its Graphics RAM (GRAM). Therefore, true alpha blending by reading the physical screen's current state is not possible.
* This library overcomes this by maintaining a **software framebuffer**. The `draw_image_rgba_composited` method blends against this in-memory representation.
* While the software framebuffer enables correct alpha blending and high-quality anti-aliased rendering for primitives, there is a performance consideration:
    * Opaque primitives update the software framebuffer (Pillow operation) and then the corresponding region on the hardware.
    * `draw_image_rgba_composited` involves cropping from the framebuffer, alpha compositing (Pillow operation), pasting back to the framebuffer, and then updating the hardware.
* For very high-speed animations that do not require alpha blending, directly using `draw_image_rgb565` (if you manage the buffer yourself and don't need the software framebuffer's state) might be faster but bypasses the benefits of the software framebuffer.

## How to Draw Transparent Primitives (e.g., Anti-aliased Line)

If you need a primitive like a line or circle to be drawn with smooth (anti-aliased) edges and blend correctly with a complex background (not just a solid color fill of the primitive itself):

1.  **Create a small Pillow `Image` in "RGBA" mode.** Make its background fully transparent (e.g., `(0,0,0,0)`).
2.  **Draw your primitive** (line, circle outline, etc.) onto this RGBA image using `ImageDraw`. Use the desired color and an alpha value of 255 (fully opaque for the primitive itself, but the anti-aliased edges will have varying alpha values against the transparent image background).
3.  **Call `display.draw_image_rgba_composited(x, y, your_rgba_primitive_image)`**. This will correctly blend your anti-aliased primitive onto the current content of the software framebuffer.

This technique is demonstrated in the `unihiker_cat_drawing_v2.py` script (not part of this library file, but a good usage example).
