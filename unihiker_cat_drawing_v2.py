import time
import math 
import os 
from pinpong.board import Board, Pin, SPI 

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False
    print("--------------------------------------------------------------------")
    print("Warning: Pillow (PIL) library not found or failed to import.")
    print("Drawing functions will not work.")
    print("Please install it on your Unihiker: pip install Pillow")
    print("--------------------------------------------------------------------")

# Import from the cleaned library with software framebuffer support
try:
    # Ensure this matches the filename of your GC9A01 library
    from GC9A01 import GC9A01 
except ImportError:
    print("Error: Could not import GC9A01 class from gc9a01_alpha_blend_mod.py.")
    print("Make sure the cleaned library file is in the same directory and named correctly.")
    if 'GC9A01' not in globals(): 
        print("GC9A01 class not found. Exiting.")
        exit()
    else:
        print("Warning: Imported GC9A01 globally. Ensure it's the version with software framebuffer.")


def create_line_rgba_image(x0, y0, x1, y1, line_color_rgb888_alpha, line_width):
    """
    Creates a Pillow RGBA image containing just a single line.
    The line is drawn relative to the top-left of its own tight bounding box.
    Returns the RGBA image, and its calculated top-left (x,y) position on the screen.
    """
    if not _HAS_PIL: return None, 0, 0
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)

    padding = (line_width // 2) + 2 
    
    # Absolute screen coordinates for the bounding box of this line image
    img_screen_x0 = min(x0, x1) - padding
    img_screen_y0 = min(y0, y1) - padding
    img_screen_x1 = max(x0, x1) + padding
    img_screen_y1 = max(y0, y1) + padding

    img_pil_width = img_screen_x1 - img_screen_x0 + 1
    img_pil_height = img_screen_y1 - img_screen_y0 + 1
        
    # Line coordinates relative to this new image's top-left corner
    rel_x0 = x0 - img_screen_x0
    rel_y0 = y0 - img_screen_y0
    rel_x1 = x1 - img_screen_x0
    rel_y1 = y1 - img_screen_y0

    if img_pil_width <= 0 or img_pil_height <= 0: return None, 0, 0

    line_img = Image.new("RGBA", (img_pil_width, img_pil_height), (0,0,0,0)) # Fully transparent
    draw_context = ImageDraw.Draw(line_img)
    draw_context.line([(rel_x0, rel_y0), (rel_x1, rel_y1)], fill=line_color_rgb888_alpha, width=line_width)
    
    return line_img, img_screen_x0, img_screen_y0


# --- Main Cat Drawing Program ---
if __name__ == "__main__":
    if not _HAS_PIL:
        print("Pillow library is required for this script. Please install it.")
        exit()

    # Initialize PinPong Board
    try:
        Board("UNIHIKER").begin()
        print("Unihiker board initialized.")
    except Exception as e:
        print(f"Error initializing Unihiker board: {e}")
        exit()

    # Pin Definitions
    CS_PIN_NUM, DC_PIN_NUM, RST_PIN_NUM, BL_PIN_NUM = 16, 12, 7, 6
    MADCTL_VALUE_TO_USE = 0x08

    # Initialize Pins and SPI
    spi_bus_obj, dc_pin, rst_pin, bl_pin_obj = None, None, None, None
    try:
        cs_pin_for_spi_init = Pin(CS_PIN_NUM)
        dc_pin = Pin(DC_PIN_NUM, Pin.OUT)
        rst_pin = Pin(RST_PIN_NUM, Pin.OUT)
        if BL_PIN_NUM is not None: bl_pin_obj = Pin(BL_PIN_NUM, Pin.OUT)
        spi_bus_obj = SPI(1, cs=cs_pin_for_spi_init, baudrate=40000000, polarity=0, phase=0)
    except Exception as e:
        print(f"Error initializing Pins or SPI: {e}")
        exit()

    # Initialize Display
    display = None
    if spi_bus_obj and dc_pin and rst_pin:
        display = GC9A01(spi_bus=spi_bus_obj, dc_pin_obj=dc_pin, rst_pin_obj=rst_pin,
                         cs_pin_obj=None, bl_pin_obj=bl_pin_obj,
                         width=240, height=240, madctl_val=MADCTL_VALUE_TO_USE)
        display.init_display() # This initializes the software framebuffer
        if bl_pin_obj: display.backlight_on()
        print("Display initialized.")
    else:
        print("Display driver not initialized due to SPI or Pin setup failure.")
        exit()

    # --- Define Colors (RGB888 tuples for Pillow drawing) ---
    COLOR_SKY_BLUE_RGB = (135, 206, 235)   # Screen Background
    COLOR_LIGHT_GRAY_RGB = (200, 200, 200) # Cat head, body
    COLOR_DARK_GRAY_RGB = (80, 80, 80)     # Outlines
    COLOR_PINK_RGB = (255, 192, 203)       # Nose
    COLOR_GREEN_RGB = (0, 200, 0)          # Eyes sclera
    COLOR_BLACK_RGB = (0, 0, 0)            # Pupils, eye outlines
    OPAQUE_ALPHA_TUPLE = (255,) # For RGBA colors (R,G,B,A)

    # Convert screen background to RGB565 for initial fill_screen
    SCREEN_BG_565 = display._rgb888_tuple_to_rgb565_int(COLOR_SKY_BLUE_RGB)

    # --- Drawing the Cat (Revised Order) ---
    print("Drawing a cat using software framebuffer and RGBA compositing...")
    # 1. Fill screen with overall background (updates software FB and HW)
    display.fill_screen(SCREEN_BG_565)
    time.sleep(0.1) 

    # --- Define Cat's Geometry ---
    head_radius = 45
    head_center_x = display.width // 2
    head_center_y = 85 

    body_width = 75 
    body_height = 90
    body_x = head_center_x - body_width // 2
    body_y = head_center_y + head_radius - 15 # Top of body Y, slight overlap with head

    # 2. Tail (Drawn BEFORE Body, composited onto sky blue)
    tail_start_x = body_x + body_width -5 
    tail_start_y = body_y + body_height * 0.6 
    tail_mid_x = tail_start_x + 35
    tail_mid_y = tail_start_y - 25
    tail_end_x = tail_start_x + 25
    tail_end_y = tail_start_y - 50
    tail_body_width = 6
    tail_outline_width = tail_body_width + 4 
    
    line_img, lx, ly = create_line_rgba_image(tail_start_x, tail_start_y, tail_mid_x, tail_mid_y, COLOR_DARK_GRAY_RGB + OPAQUE_ALPHA_TUPLE, tail_outline_width)
    if line_img: display.draw_image_rgba_composited(lx, ly, line_img)
    line_img, lx, ly = create_line_rgba_image(tail_start_x, tail_start_y, tail_mid_x, tail_mid_y, COLOR_LIGHT_GRAY_RGB + OPAQUE_ALPHA_TUPLE, tail_body_width)
    if line_img: display.draw_image_rgba_composited(lx, ly, line_img)
    line_img, lx, ly = create_line_rgba_image(tail_mid_x, tail_mid_y, tail_end_x, tail_end_y, COLOR_DARK_GRAY_RGB + OPAQUE_ALPHA_TUPLE, tail_outline_width - 2)
    if line_img: display.draw_image_rgba_composited(lx, ly, line_img)
    line_img, lx, ly = create_line_rgba_image(tail_mid_x, tail_mid_y, tail_end_x, tail_end_y, COLOR_LIGHT_GRAY_RGB + OPAQUE_ALPHA_TUPLE, tail_body_width - 2)
    if line_img: display.draw_image_rgba_composited(lx, ly, line_img)

    # 3. Body & Legs (Opaque, drawn using standard library methods)
    body_fill_565 = display._rgb888_tuple_to_rgb565_int(COLOR_LIGHT_GRAY_RGB)
    body_outline_565 = display._rgb888_tuple_to_rgb565_int(COLOR_DARK_GRAY_RGB)
    display.rectangle(body_x, body_y, body_width, body_height, 
                      fill_rgb565=body_fill_565, 
                      outline_rgb565=body_outline_565, outline_width=2)
    leg_width = 18
    leg_height = 35
    leg_y_start = body_y + body_height - (leg_height // 2.5) 
    display.rectangle(body_x + 8, leg_y_start, leg_width, leg_height, 
                      fill_rgb565=body_fill_565, outline_rgb565=body_outline_565, outline_width=2)
    display.rectangle(body_x + body_width - leg_width - 8, leg_y_start, leg_width, leg_height, 
                      fill_rgb565=body_fill_565, outline_rgb565=body_outline_565, outline_width=2)

    # 4. Head (Opaque, drawn using standard library method. Will overlap body top.)
    display.circle(head_center_x, head_center_y, head_radius,
                   fill_rgb565=body_fill_565, 
                   outline_rgb565=body_outline_565, 
                   outline_width=2) 

    # 5. Ears (Drawn AFTER Head, as RGBA images composited)
    ear_line_width = 2
    tip_y_factor = 1.1  
    outer_base_y_factor = 0.6 
    inner_base_y_factor = 0.45 
    # Left Ear
    ear_left_tip_x = head_center_x - head_radius * 0.5
    ear_left_tip_y = head_center_y - head_radius * tip_y_factor 
    ear_left_base_outer_x = head_center_x - head_radius * 0.8 
    ear_left_base_outer_y = head_center_y - head_radius * outer_base_y_factor
    ear_left_base_inner_x = head_center_x - head_radius * 0.2 
    ear_left_base_inner_y = head_center_y - head_radius * inner_base_y_factor
    line_img, lx, ly = create_line_rgba_image(ear_left_tip_x, ear_left_tip_y, ear_left_base_outer_x, ear_left_base_outer_y, COLOR_DARK_GRAY_RGB + OPAQUE_ALPHA_TUPLE, ear_line_width)
    if line_img: display.draw_image_rgba_composited(lx, ly, line_img)
    line_img, lx, ly = create_line_rgba_image(ear_left_tip_x, ear_left_tip_y, ear_left_base_inner_x, ear_left_base_inner_y, COLOR_DARK_GRAY_RGB + OPAQUE_ALPHA_TUPLE, ear_line_width)
    if line_img: display.draw_image_rgba_composited(lx, ly, line_img)
    line_img, lx, ly = create_line_rgba_image(ear_left_base_outer_x, ear_left_base_outer_y, ear_left_base_inner_x, ear_left_base_inner_y, COLOR_DARK_GRAY_RGB + OPAQUE_ALPHA_TUPLE, ear_line_width)
    if line_img: display.draw_image_rgba_composited(lx, ly, line_img)
    # Right Ear
    ear_right_tip_x = head_center_x + head_radius * 0.5
    ear_right_tip_y = head_center_y - head_radius * tip_y_factor
    ear_right_base_outer_x = head_center_x + head_radius * 0.8 
    ear_right_base_outer_y = head_center_y - head_radius * outer_base_y_factor
    ear_right_base_inner_x = head_center_x + head_radius * 0.2 
    ear_right_base_inner_y = head_center_y - head_radius * inner_base_y_factor
    line_img, lx, ly = create_line_rgba_image(ear_right_tip_x, ear_right_tip_y, ear_right_base_outer_x, ear_right_base_outer_y, COLOR_DARK_GRAY_RGB + OPAQUE_ALPHA_TUPLE, ear_line_width)
    if line_img: display.draw_image_rgba_composited(lx, ly, line_img)
    line_img, lx, ly = create_line_rgba_image(ear_right_tip_x, ear_right_tip_y, ear_right_base_inner_x, ear_right_base_inner_y, COLOR_DARK_GRAY_RGB + OPAQUE_ALPHA_TUPLE, ear_line_width)
    if line_img: display.draw_image_rgba_composited(lx, ly, line_img)
    line_img, lx, ly = create_line_rgba_image(ear_right_base_outer_x, ear_right_base_outer_y, ear_right_base_inner_x, ear_right_base_inner_y, COLOR_DARK_GRAY_RGB + OPAQUE_ALPHA_TUPLE, ear_line_width)
    if line_img: display.draw_image_rgba_composited(lx, ly, line_img)

    # 6. Eyes (Opaque, drawn using standard library method on the head)
    eye_radius = 10; eye_offset_x = 20; eye_offset_y = -8; pupil_radius = 4
    eye_sclera_565 = display._rgb888_tuple_to_rgb565_int(COLOR_GREEN_RGB)
    eye_outline_565 = display._rgb888_tuple_to_rgb565_int(COLOR_BLACK_RGB)
    pupil_fill_565 = display._rgb888_tuple_to_rgb565_int(COLOR_BLACK_RGB)
    display.circle(head_center_x - eye_offset_x, head_center_y + eye_offset_y, eye_radius, fill_rgb565=eye_sclera_565, outline_rgb565=eye_outline_565, outline_width=1) 
    display.circle(head_center_x - eye_offset_x, head_center_y + eye_offset_y, pupil_radius, fill_rgb565=pupil_fill_565)    
    display.circle(head_center_x + eye_offset_x, head_center_y + eye_offset_y, eye_radius, fill_rgb565=eye_sclera_565, outline_rgb565=eye_outline_565, outline_width=1) 
    display.circle(head_center_x + eye_offset_x, head_center_y + eye_offset_y, pupil_radius, fill_rgb565=pupil_fill_565)    

    # 7. Nose (Opaque, drawn using standard library method on the head)
    nose_radius = 6; nose_y_offset = head_radius * 0.35
    nose_fill_565 = display._rgb888_tuple_to_rgb565_int(COLOR_PINK_RGB)
    nose_outline_565 = display._rgb888_tuple_to_rgb565_int(COLOR_DARK_GRAY_RGB)
    display.circle(head_center_x, head_center_y + nose_y_offset, nose_radius, fill_rgb565=nose_fill_565, outline_rgb565=nose_outline_565, outline_width=1) 
        
    # 8. Mouth (Drawn as RGBA images composited onto the head)
    mouth_y_base = head_center_y + nose_y_offset + nose_radius + 1
    mouth_width_half = 10; mouth_depth = 6; mouth_line_width = 2
    line_img, lx, ly = create_line_rgba_image(head_center_x, mouth_y_base, head_center_x - mouth_width_half, mouth_y_base + mouth_depth, COLOR_DARK_GRAY_RGB + OPAQUE_ALPHA_TUPLE, mouth_line_width)
    if line_img: display.draw_image_rgba_composited(lx, ly, line_img)
    line_img, lx, ly = create_line_rgba_image(head_center_x, mouth_y_base, head_center_x + mouth_width_half, mouth_y_base + mouth_depth, COLOR_DARK_GRAY_RGB + OPAQUE_ALPHA_TUPLE, mouth_line_width)
    if line_img: display.draw_image_rgba_composited(lx, ly, line_img)

    # 9. Whiskers (Drawn as RGBA images composited onto the head)
    whisker_len = 30; whisker_y_start_offset = head_radius * 0.25 
    whisker_x_start_offset = head_radius * 0.85; whisker_line_width = 1
    whisker_base_y_abs = head_center_y + whisker_y_start_offset
    wh_coords = [
        (head_center_x - whisker_x_start_offset, whisker_base_y_abs - 8, head_center_x - whisker_x_start_offset - whisker_len, whisker_base_y_abs - 12),
        (head_center_x - whisker_x_start_offset, whisker_base_y_abs,     head_center_x - whisker_x_start_offset - whisker_len, whisker_base_y_abs),
        (head_center_x - whisker_x_start_offset, whisker_base_y_abs + 8, head_center_x - whisker_x_start_offset - whisker_len, whisker_base_y_abs + 12),
        (head_center_x + whisker_x_start_offset, whisker_base_y_abs - 8, head_center_x + whisker_x_start_offset + whisker_len, whisker_base_y_abs - 12),
        (head_center_x + whisker_x_start_offset, whisker_base_y_abs,     head_center_x + whisker_x_start_offset + whisker_len, whisker_base_y_abs),
        (head_center_x + whisker_x_start_offset, whisker_base_y_abs + 8, head_center_x + whisker_x_start_offset + whisker_len, whisker_base_y_abs + 12)
    ]
    for x0,y0,x1,y1 in wh_coords:
        line_img, lx, ly = create_line_rgba_image(x0,y0,x1,y1, COLOR_DARK_GRAY_RGB + OPAQUE_ALPHA_TUPLE, whisker_line_width)
        if line_img: display.draw_image_rgba_composited(lx, ly, line_img)
                      
    print("Cat drawing complete!")

