# GC9A01 Display Driver for Unihiker M10
#
# This library provides a class to control GC9A01-based 240x240 round LCDs
# with a Unihiker board using PinPong for GPIO and SPI communication.
#
# Features:
# - Standard drawing methods (pixels, lines, shapes, text).
# - Software Framebuffer: Maintains an in-memory mirror of the display
#   to enable advanced compositing effects like alpha blending.
# - Alpha Blending: Supports drawing RGBA images with transparency,
#   blending them against the current content of the software framebuffer.
#
# Note on Transparency:
# - The _pil_image_to_rgb565_bytearray method itself still flattens RGBA images
#   against a BLACK background if called directly with an RGBA image.
# - However, drawing methods that use the software framebuffer (like 
#   draw_image_rgba_composited or opaque primitives) perform blending/drawing 
#   correctly against the framebuffer before conversion.

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

# --- GC9A01 Command Definitions ---
CMD_NOP = 0x00; CMD_SWRESET = 0x01; CMD_SLPIN = 0x10; CMD_SLPOUT = 0x11
CMD_INVOFF = 0x20; CMD_INVON = 0x21; CMD_DISPOFF = 0x28; CMD_DISPON = 0x29
CMD_CASET = 0x2A; CMD_RASET = 0x2B; CMD_RAMWR = 0x2C; CMD_PIXFMT = 0x3A
CMD_MADCTL = 0x36; CMD_TEON = 0x35
CMD_INTER_REGISTER_ENABLE_1 = 0xFE; CMD_INTER_REGISTER_ENABLE_2 = 0xEF

class GC9A01:
    SPI_CHUNK_SIZE_BYTES = 4096 

    def __init__(self, spi_bus, dc_pin_obj, rst_pin_obj, cs_pin_obj=None, bl_pin_obj=None, width=240, height=240, madctl_val=0x08):
        self.spi = spi_bus
        self.width = width
        self.height = height
        self.madctl_val = madctl_val 
        self.dc = dc_pin_obj
        self.rst = rst_pin_obj
        self._manual_cs = bool(cs_pin_obj)
        self.cs = cs_pin_obj
        if self._manual_cs: self.cs.value(1)
        self.bl = bl_pin_obj 
        if self.dc: self.dc.value(0)

        self.framebuffer = None
        if _HAS_PIL:
            self.framebuffer = Image.new("RGB", (self.width, self.height), (0, 0, 0)) # Default to black
            self.fb_draw = ImageDraw.Draw(self.framebuffer)
        else:
            print("Error: Pillow not found. Software framebuffer and advanced drawing disabled.")

    def _rgb565_to_rgb888_tuple(self, color_rgb565):
        r8 = (color_rgb565 & 0xF800) >> 11; g8 = (color_rgb565 & 0x07E0) >> 5; b8 = (color_rgb565 & 0x001F)
        r8 = (r8 * 255 + 15) // 31; g8 = (g8 * 255 + 31) // 63; b8 = (b8 * 255 + 15) // 31
        return (r8, g8, b8)

    def _rgb888_tuple_to_rgb565_int(self, rgb_tuple):
        if rgb_tuple is None: return None 
        r, g, b = rgb_tuple
        return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

    def _pil_image_to_rgb565_bytearray(self, pil_image):
        if pil_image.mode == "RGBA":
            # print("Warning: _pil_image_to_rgb565_bytearray received RGBA, flattening to black.")
            background = Image.new("RGB", pil_image.size, (0,0,0)) 
            background.paste(pil_image, mask=pil_image.split()[3]) 
            img_rgb = background
        elif pil_image.mode != "RGB":
            img_rgb = pil_image.convert("RGB")
        else:
            img_rgb = pil_image
        
        buffer = bytearray(img_rgb.width * img_rgb.height * 2)
        idx = 0
        for y_coord in range(img_rgb.height):
            for x_coord in range(img_rgb.width):
                r, g, b = img_rgb.getpixel((x_coord, y_coord))
                rgb565_color = self._rgb888_tuple_to_rgb565_int((r,g,b))
                buffer[idx] = (rgb565_color >> 8) & 0xFF
                buffer[idx+1] = rgb565_color & 0xFF
                idx += 2
        return buffer

    def _cs_low(self): 
        if self._manual_cs and self.cs: self.cs.value(0)
    def _cs_high(self): 
        if self._manual_cs and self.cs: self.cs.value(1)
    def _write_cmd_bytes_data(self, cmd, data_bytes=None): 
        self._cs_low(); self.dc.value(0); self.spi.write([cmd]) 
        if data_bytes is not None: self.dc.value(1); self.spi.write(list(data_bytes)) 
        self._cs_high()
    def _write_cmd_no_args(self, cmd): 
        self._cs_low(); self.dc.value(0); self.spi.write([cmd]); self._cs_high()
    def _write_cmd_single_arg(self, cmd, arg): 
        self._cs_low(); self.dc.value(0); self.spi.write([cmd])
        self.dc.value(1); self.spi.write([arg]); self._cs_high()
    def _write_data(self, data_input): 
        self._cs_low(); self.dc.value(1) 
        if isinstance(data_input, (bytes, bytearray)):
            for i in range(0, len(data_input), self.SPI_CHUNK_SIZE_BYTES):
                self.spi.write(list(data_input[i:i + self.SPI_CHUNK_SIZE_BYTES])) 
        elif isinstance(data_input, list): self.spi.write(data_input) 
        else: print(f"Error: _write_data expects list, bytes or bytearray, got {type(data_input)}")
        self._cs_high()

    def reset(self): 
        if self.rst: self.rst.value(1); time.sleep(0.01); self.rst.value(0); time.sleep(0.01); self.rst.value(1); time.sleep(0.01) 
        else: print("Warning: Reset pin not configured.")

    def init_display(self):
        self.reset()
        time.sleep(0.100) 
        self._write_cmd_no_args(0xEF); self._write_cmd_single_arg(0xEB, 0x14)
        self._write_cmd_no_args(CMD_INTER_REGISTER_ENABLE_1); self._write_cmd_no_args(CMD_INTER_REGISTER_ENABLE_2)
        self._write_cmd_single_arg(0xEB, 0x14); self._write_cmd_single_arg(0x84, 0x40) 
        self._write_cmd_single_arg(0x85, 0xFF); self._write_cmd_single_arg(0x86, 0xFF) 
        self._write_cmd_single_arg(0x87, 0xFF); self._write_cmd_single_arg(0x88, 0x0A)
        self._write_cmd_single_arg(0x89, 0x21); self._write_cmd_single_arg(0x8A, 0x00)
        self._write_cmd_single_arg(0x8B, 0x80); self._write_cmd_single_arg(0x8C, 0x01) 
        self._write_cmd_single_arg(0x8D, 0x01); self._write_cmd_single_arg(0x8E, 0xFF) 
        self._write_cmd_single_arg(0x8F, 0xFF); self._write_cmd_bytes_data(0xB6, b'\x00\x20') 
        self._write_cmd_single_arg(CMD_MADCTL, self.madctl_val); self._write_cmd_single_arg(CMD_PIXFMT, 0x05)
        self._write_cmd_bytes_data(0x90, b'\x08\x08\x08\x08'); self._write_cmd_single_arg(0xBD, 0x06)
        self._write_cmd_single_arg(0xBC, 0x00); self._write_cmd_bytes_data(0xFF, b'\x60\x01\x04') 
        self._write_cmd_single_arg(0xC3, 0x13); self._write_cmd_single_arg(0xC4, 0x13) 
        self._write_cmd_single_arg(0xC9, 0x22); self._write_cmd_single_arg(0xBE, 0x11)
        self._write_cmd_bytes_data(0xE1, b'\x10\x0E'); self._write_cmd_bytes_data(0xDF, b'\x21\x0c\x02')
        self._write_cmd_bytes_data(0xF0, b'\x45\x09\x08\x08\x26\x2A'); self._write_cmd_bytes_data(0xF1, b'\x43\x70\x72\x36\x37\x6F')
        self._write_cmd_bytes_data(0xF2, b'\x45\x09\x08\x08\x26\x2A'); self._write_cmd_bytes_data(0xF3, b'\x43\x70\x72\x36\x37\x6F')
        self._write_cmd_bytes_data(0xED, b'\x1B\x0B'); self._write_cmd_single_arg(0xAE, 0x77)
        self._write_cmd_single_arg(0xCD, 0x63); self._write_cmd_bytes_data(0x70, b'\x07\x07\x04\x0E\x0F\x09\x07\x08\x03')
        self._write_cmd_single_arg(0xE8, 0x34); self._write_cmd_bytes_data(0x62, b'\x18\x0D\x71\xED\x70\x70\x18\x0F\x71\xEF\x70\x70')
        self._write_cmd_bytes_data(0x63, b'\x18\x11\x71\xF1\x70\x70\x18\x13\x71\xF3\x70\x70'); self._write_cmd_bytes_data(0x64, b'\x28\x29\xF1\x01\xF1\x00\x07')
        self._write_cmd_bytes_data(0x66, b'\x3C\x00\xCD\x67\x45\x45\x10\x00\x00\x00'); self._write_cmd_bytes_data(0x67, b'\x00\x3C\x00\x00\x00\x01\x54\x10\x32\x98')
        self._write_cmd_bytes_data(0x74, b'\x10\x85\x80\x00\x00\x4E\x00'); self._write_cmd_bytes_data(0x98, b'\x3e\x07')
        self._write_cmd_no_args(CMD_TEON); self._write_cmd_no_args(CMD_INVON)  
        self._write_cmd_no_args(CMD_SLPOUT); time.sleep(0.12) 
        self._write_cmd_no_args(CMD_DISPON); time.sleep(0.02) 
        if self.bl: self.backlight_on()
        if self.framebuffer: # Initialize framebuffer to black upon display init
            self.fb_draw.rectangle([(0,0), (self.width, self.height)], fill=(0,0,0))
        print("GC9A01 display initialized.")
        
    def display_on(self):
        self._write_cmd_no_args(CMD_DISPON); time.sleep(0.01) 
    def display_off(self):
        self._write_cmd_no_args(CMD_DISPOFF); time.sleep(0.01)
    def backlight_on(self):
        if self.bl: self.bl.value(1)
    def backlight_off(self):
        if self.bl: self.bl.value(0)

    def set_window(self, x_start, y_start, x_end, y_end): 
        x_start=max(0,min(int(x_start),self.width-1)); y_start=max(0,min(int(y_start),self.height-1))
        x_end=max(0,min(int(x_end),self.width-1)); y_end=max(0,min(int(y_end),self.height-1))
        if x_start > x_end: x_start, x_end = x_end, x_start 
        if y_start > y_end: y_start, y_end = y_end, y_start
        self._write_cmd_bytes_data(CMD_CASET, bytes([(x_start>>8)&0xFF, x_start&0xFF, (x_end>>8)&0xFF, x_end&0xFF]))
        self._write_cmd_bytes_data(CMD_RASET, bytes([(y_start>>8)&0xFF, y_start&0xFF, (y_end>>8)&0xFF, y_end&0xFF]))
    
    def write_ram_prepare(self): 
        self._write_cmd_no_args(CMD_RAMWR)

    def _update_framebuffer_region(self, x, y, width, height):
        """Helper to update a region of the physical display from the software framebuffer."""
        if not self.framebuffer or not _HAS_PIL: return
        x, y, width, height = int(x), int(y), int(width), int(height)
        # Ensure region is within bounds
        x = max(0, min(x, self.width -1))
        y = max(0, min(y, self.height -1))
        width = max(0, min(width, self.width - x))
        height = max(0, min(height, self.height - y))
        if width == 0 or height == 0: return

        try:
            region_img = self.framebuffer.crop((x, y, x + width, y + height))
            rgb565_buffer = self._pil_image_to_rgb565_bytearray(region_img)
            self.draw_image_rgb565(x, y, width, height, rgb565_buffer)
        except Exception as e:
            print(f"Error updating framebuffer region to hardware: {e}")

    def draw_image_rgb(self, x, y, pil_image_rgb):
        """
        Draws a Pillow RGB image, updating software framebuffer and physical display.
        """
        if not _HAS_PIL or not self.framebuffer: print("Error: Pillow or framebuffer not available."); return
        x_int, y_int = int(x), int(y)
        if pil_image_rgb.mode != "RGB":
            pil_image_rgb = pil_image_rgb.convert("RGB")
        
        # Paste onto software framebuffer (Pillow handles clipping for paste if image is larger)
        self.framebuffer.paste(pil_image_rgb, (x_int, y_int))
        
        # Update the corresponding region on the physical display
        self._update_framebuffer_region(x_int, y_int, pil_image_rgb.width, pil_image_rgb.height)

    def draw_image_rgba_composited(self, x, y, pil_image_rgba):
        """
        Draws an RGBA image, alpha-compositing it with the current software framebuffer.
        Updates both the software framebuffer and the physical display.
        """
        if not _HAS_PIL or not self.framebuffer:
            print("Error: Pillow or framebuffer not available for RGBA compositing.")
            if _HAS_PIL and pil_image_rgba: # Fallback if framebuffer is somehow None
                rgb_buffer = self._pil_image_to_rgb565_bytearray(pil_image_rgba) 
                self.draw_image_rgb565(int(x), int(y), pil_image_rgba.width, pil_image_rgba.height, rgb_buffer)
            return
        
        if pil_image_rgba.mode != "RGBA":
            pil_image_rgba = pil_image_rgba.convert("RGBA")

        img_width, img_height = pil_image_rgba.size
        x_int, y_int = int(x), int(y)

        # Determine the actual drawing area on the screen (clipped)
        draw_x_on_screen = max(0, x_int)
        draw_y_on_screen = max(0, y_int)
        
        # Determine what part of the source RGBA image to use
        src_crop_x0 = 0 if x_int >= 0 else -x_int
        src_crop_y0 = 0 if y_int >= 0 else -y_int
        
        blit_width = min(img_width - src_crop_x0, self.width - draw_x_on_screen)
        blit_height = min(img_height - src_crop_y0, self.height - draw_y_on_screen)

        if blit_width <= 0 or blit_height <= 0: return 

        fg_cropped_rgba = pil_image_rgba.crop((src_crop_x0, src_crop_y0, src_crop_x0 + blit_width, src_crop_y0 + blit_height))
        
        # Get background region from software framebuffer
        bg_region_rgb = self.framebuffer.crop((draw_x_on_screen, draw_y_on_screen, draw_x_on_screen + blit_width, draw_y_on_screen + blit_height))
        bg_region_rgba = bg_region_rgb.convert("RGBA") # Convert to RGBA for alpha_composite

        # Composite
        composited_region_rgba = Image.alpha_composite(bg_region_rgba, fg_cropped_rgba)
        composited_region_rgb = composited_region_rgba.convert("RGB") # Back to RGB

        # Update software framebuffer
        self.framebuffer.paste(composited_region_rgb, (draw_x_on_screen, draw_y_on_screen))
        
        # Update physical display with this composited region
        self._update_framebuffer_region(draw_x_on_screen, draw_y_on_screen, blit_width, blit_height)

    def draw_image_rgb565(self, x, y, width, height, image_buffer_bytes):
        """Low-level: Draws raw RGB565 buffer to hardware. DOES NOT update software framebuffer."""
        x_int, y_int = int(x), int(y) # Ensure integer coords
        if x_int >= self.width or y_int >= self.height or x_int + width <= 0 or y_int + height <= 0: return
        src_x_offset = 0; src_y_offset = 0
        if x_int < 0: src_x_offset = -x_int
        if y_int < 0: src_y_offset = -y_int
        draw_x_on_screen = max(0, x_int)
        draw_y_on_screen = max(0, y_int)
        blit_width = min(width - src_x_offset, self.width - draw_x_on_screen)
        blit_height = min(height - src_y_offset, self.height - draw_y_on_screen)
        if blit_width <= 0 or blit_height <= 0: return
        
        self.set_window(draw_x_on_screen, draw_y_on_screen, draw_x_on_screen + blit_width - 1, draw_y_on_screen + blit_height - 1)
        self.write_ram_prepare()
        if blit_width != width or blit_height != height or src_x_offset > 0 or src_y_offset > 0:
            clipped_buffer = bytearray(blit_width * blit_height * 2)
            dest_idx = 0
            for row_idx in range(blit_height):
                s_start = ((src_y_offset + row_idx) * width + src_x_offset) * 2
                s_end = s_start + blit_width * 2
                clipped_buffer[dest_idx : dest_idx + blit_width * 2] = image_buffer_bytes[s_start : s_end]
                dest_idx += blit_width * 2
            self._write_data(clipped_buffer)
        else:
            self._write_data(image_buffer_bytes)

    # --- Standard Drawing Methods (Update SW Framebuffer & Physical Display) ---
    def pixel(self, x, y, color_rgb565):
        if not _HAS_PIL or not self.framebuffer: return
        x_int, y_int = int(x), int(y)
        if not (0 <= x_int < self.width and 0 <= y_int < self.height): return
        pil_color_rgb888 = self._rgb565_to_rgb888_tuple(color_rgb565)
        self.fb_draw.point((x_int,y_int), fill=pil_color_rgb888)
        self._update_framebuffer_region(x_int, y_int, 1, 1)

    def line(self, x0, y0, x1, y1, color_rgb565, line_width=1):
        if not _HAS_PIL or not self.framebuffer: return
        x0i,y0i,x1i,y1i = int(x0),int(y0),int(x1),int(y1)
        pil_color_rgb888 = self._rgb565_to_rgb888_tuple(color_rgb565)
        self.fb_draw.line([(x0i,y0i),(x1i,y1i)], fill=pil_color_rgb888, width=line_width)
        
        # Determine bounding box of the line for update
        padding = (line_width // 2) + 1 
        min_x = min(x0i, x1i) - padding; max_x = max(x0i, x1i) + padding
        min_y = min(y0i, y1i) - padding; max_y = max(y0i, y1i) + padding
        
        update_x = max(0, min_x); update_y = max(0, min_y)
        update_w = min(max_x, self.width-1) - update_x + 1
        update_h = min(max_y, self.height-1) - update_y + 1
        self._update_framebuffer_region(update_x, update_y, update_w, update_h)

    def rectangle(self, x, y, width, height, outline_rgb565=None, fill_rgb565=None, outline_width=1):
        if not _HAS_PIL or not self.framebuffer: return
        x_int,y_int,w_int,h_int = int(x),int(y),int(width),int(height)
        if w_int<=0 or h_int<=0: return

        pil_fill_rgb888 = self._rgb565_to_rgb888_tuple(fill_rgb565) if fill_rgb565 is not None else None
        pil_outline_rgb888 = self._rgb565_to_rgb888_tuple(outline_rgb565) if outline_rgb565 is not None else None
        
        self.fb_draw.rectangle([(x_int,y_int),(x_int+w_int-1,y_int+h_int-1)], 
                               fill=pil_fill_rgb888, 
                               outline=pil_outline_rgb888, 
                               width=outline_width if pil_outline_rgb888 and outline_width > 0 else 0)
        
        # Determine bounding box for update
        padding = (outline_width // 2) + 1 if pil_outline_rgb888 and outline_width > 0 else 0
        self._update_framebuffer_region(x_int - padding, y_int - padding, w_int + 2*padding, h_int + 2*padding)

    def fill_rect(self, x, y, width, height, color_rgb565):
        self.rectangle(x,y,width,height,fill_rgb565=color_rgb565, outline_rgb565=None)

    def fill_screen(self, color_rgb565):
        if not _HAS_PIL or not self.framebuffer: return
        pil_color_rgb888 = self._rgb565_to_rgb888_tuple(color_rgb565)
        self.fb_draw.rectangle([(0,0), (self.width-1, self.height-1)], fill=pil_color_rgb888)
        self._update_framebuffer_region(0,0,self.width,self.height)
        
    def circle(self, x_center, y_center, radius, outline_rgb565=None, fill_rgb565=None, outline_width=1):
        if not _HAS_PIL or not self.framebuffer: return
        x_c,y_c,r = int(x_center),int(y_center),int(radius)
        if r<0: return
        if r==0: self.pixel(x_c,y_c, fill_rgb565 if fill_rgb565 is not None else outline_rgb565); return

        pil_fill_rgb888 = self._rgb565_to_rgb888_tuple(fill_rgb565) if fill_rgb565 is not None else None
        pil_outline_rgb888 = self._rgb565_to_rgb888_tuple(outline_rgb565) if outline_rgb565 is not None else None

        self.fb_draw.ellipse([(x_c-r, y_c-r), (x_c+r, y_c+r)], 
                             fill=pil_fill_rgb888, 
                             outline=pil_outline_rgb888, 
                             width=outline_width if pil_outline_rgb888 and outline_width > 0 else 0)
        
        padding = (outline_width // 2) + 1 if pil_outline_rgb888 and outline_width > 0 else 1
        self._update_framebuffer_region(x_c-r-padding, y_c-r-padding, 2*(r+padding), 2*(r+padding))

    def text(self, x, y, text_string, font_path, font_size, text_color_rgb888, background_color_rgb888=None):
        if not _HAS_PIL or not self.framebuffer: print("Error: Pillow or framebuffer not available."); return
        x_int, y_int = int(x), int(y)
        try: font = ImageFont.truetype(font_path, font_size)
        except IOError: print(f"Error: Font '{font_path}' not found."); return
        except Exception as e: print(f"Error loading font: {e}"); return

        # Get text dimensions using a temporary draw object for accuracy
        temp_draw = ImageDraw.Draw(Image.new("RGB",(1,1))) # Minimal temp image
        try:
            if hasattr(temp_draw, 'textbbox') and hasattr(font, 'getbbox'): # Preferable for modern Pillow
                 # anchor='lt' means x,y is top-left of the ink bounding box
                 bbox = temp_draw.textbbox((0,0),text_string,font=font,anchor="lt") 
                 txt_w,txt_h = bbox[2]-bbox[0], bbox[3]-bbox[1]
            else: # Fallback for older Pillow
                txt_w,txt_h = temp_draw.textsize(text_string,font=font)
        except Exception as e: print(f"Error getting text dimensions: {e}"); return
        if txt_w<=0 or txt_h<=0: return
        
        # If background is specified, draw it first on the framebuffer
        if background_color_rgb888:
            self.fb_draw.rectangle([(x_int, y_int), (x_int+txt_w-1, y_int+txt_h-1)], fill=background_color_rgb888)
        
        # Draw text onto software framebuffer
        # Pillow's text drawing will anti-alias against what's already in self.framebuffer
        # (or the background_color_rgb888 if we drew it above)
        if hasattr(self.fb_draw, 'textbbox') and hasattr(font, 'getbbox'):
            self.fb_draw.text((x_int,y_int), text_string, font=font, fill=text_color_rgb888, anchor="lt")
        else:
            self.fb_draw.text((x_int,y_int), text_string, font=font, fill=text_color_rgb888)
            
        # Update the region on the physical display
        self._update_framebuffer_region(x_int, y_int, txt_w, txt_h)


# --- Example Usage ---
if __name__ == "__main__":
    print("GC9A01 Drawing Example with Software Framebuffer and Alpha Compositing")
    
    CS_PIN_NUM, DC_PIN_NUM, RST_PIN_NUM, BL_PIN_NUM = 16, 12, 7, 6
    MADCTL_VALUE_TO_USE = 0x08 
    FONT_PATH = "DejaVuSans-Bold.ttf" 

    board_initialized = False
    try:
        Board("UNIHIKER").begin(); board_initialized = True
        print("Unihiker board initialized.")
    except Exception as e: print(f"Error initializing Unihiker board: {e}")

    if board_initialized and _HAS_PIL:
        display = None
        try:
            cs_pin = Pin(CS_PIN_NUM); dc_pin = Pin(DC_PIN_NUM, Pin.OUT); rst_pin = Pin(RST_PIN_NUM, Pin.OUT)
            bl_pin_obj = Pin(BL_PIN_NUM, Pin.OUT) if BL_PIN_NUM is not None else None
            # For Unihiker, SPI constructor cs parameter expects a Pin object.
            spi_bus = SPI(1, cs=cs_pin, baudrate=40000000, polarity=0, phase=0) 
            
            display = GC9A01(spi_bus=spi_bus, dc_pin_obj=dc_pin, rst_pin_obj=rst_pin, 
                             cs_pin_obj=None, # Set to None as SPI class handles CS via its cs_pin parameter
                             bl_pin_obj=bl_pin_obj, madctl_val=MADCTL_VALUE_TO_USE)
            display.init_display() 
            print("Display initialized.")

            # 1. Fill screen with a base color
            screen_bg_color_rgb = (0, 50, 100) # Dark Teal
            screen_bg_color_565 = display._rgb888_tuple_to_rgb565_int(screen_bg_color_rgb)
            display.fill_screen(screen_bg_color_565) 
            print(f"Screen filled with RGB: {screen_bg_color_rgb}")
            time.sleep(0.5)

            # 2. Draw some opaque shapes using standard methods (will update SW FB and HW)
            display.fill_rect(10,10, 50, 50, display._rgb888_tuple_to_rgb565_int((200,0,0))) 
            display.line(5, 70, 235, 70, display._rgb888_tuple_to_rgb565_int((255,255,255)), 3) 
            time.sleep(0.5)

            # 3. Create a semi-transparent RGBA Pillow image
            circle_img_rgba = Image.new("RGBA", (100, 100), (0,0,0,0)) 
            draw_circle = ImageDraw.Draw(circle_img_rgba)
            draw_circle.ellipse([(5,5), (95,95)], fill=(0, 255, 0, 128), outline=(255,255,0,200), width=4) 

            # 4. Draw it using the new alpha compositing method
            print("Drawing semi-transparent green circle (composited with SW framebuffer)...")
            display.draw_image_rgba_composited(70, 40, circle_img_rgba) 
            time.sleep(1)

            # 5. Draw another semi-transparent shape overlapping the first
            rect_img_rgba = Image.new("RGBA", (120, 60), (255, 0, 255, 150)) 
            try:
                font_for_rect = ImageFont.truetype(FONT_PATH, 15)
            except IOError:
                font_for_rect = ImageFont.load_default() # Fallback font
            ImageDraw.Draw(rect_img_rgba).text((5,5), "Alpha!", font=font_for_rect, fill=(255,255,255,255)) # Opaque white text on magenta

            print("Drawing semi-transparent magenta rectangle (composited with SW framebuffer)...")
            display.draw_image_rgba_composited(30, 100, rect_img_rgba)
            time.sleep(1)

            # 6. Text with specific background (not using alpha compositing for this one, but drawn on FB)
            actual_font_path = FONT_PATH
            if not os.path.exists(FONT_PATH): # Simple check
                font_paths_to_try = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
                actual_font_path = next((fp for fp in font_paths_to_try if os.path.exists(fp)), None)
            
            if actual_font_path:
                display.text(10, 180, "Opaque BG Text", actual_font_path, 20, (255,255,0), (50,50,50)) # Yellow on Gray
            else: print(f"Font for text example not found. Searched '{FONT_PATH}' and fallbacks."); 
            
            print("Example finished. Check the display.")

        except Exception as e:
            print(f"An error occurred during the example: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if display and display.bl: pass 
            print("Cleanup: Example ended.")
            
    elif not _HAS_PIL: print("Pillow library not found.")
    elif not board_initialized: print("Board not initialized.")

