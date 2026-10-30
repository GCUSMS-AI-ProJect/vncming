#ifndef VNCMING_TOOLBAR_RESOLUTION_CHOICE_H
#define VNCMING_TOOLBAR_RESOLUTION_CHOICE_H

#include "MacMotion.h"

// Unlike Fl_Choice's selected-item alignment, always open below the toolbar.
class ToolbarResolutionChoice : public ModernChoice {
public:
  ToolbarResolutionChoice(int x, int y, int w, int h)
    : ModernChoice(x, y, w, h) {}

  void draw() {
    draw_box(box(), color());
    if (mvalue()) {
      fl_push_clip(x()+12, y()+4, std::max(0,w()-44), h()-8);
      fl_font(textfont(), textsize());
      fl_color(textcolor());
      fl_draw(mvalue()->label(), x()+12, y()+4, std::max(0,w()-44), h()-8, FL_ALIGN_LEFT);
      fl_pop_clip();
    }
    fl_color(fl_rgb_color(128,116,106));
    fl_line_style(FL_SOLID, 2);
    fl_line(x()+w()-25, y()+h()/2-2, x()+w()-21, y()+h()/2+2,
            x()+w()-17, y()+h()/2-2);
    fl_line_style(0);
    if (Fl::focus() == this) draw_focus(box(), x()+2, y()+2, w()-4, h()-4);
  }

  int handle(int event) {
    bool keyboard = event == FL_KEYBOARD &&
      (Fl::event_key() == ' ' || Fl::event_key() == FL_Enter ||
       Fl::event_key() == FL_KP_Enter || Fl::event_key() == FL_Down);
    if (event != FL_PUSH && !keyboard) return ModernChoice::handle(event);
    if (!menu() || !menu()->text) return 0;
    Fl_Widget_Tracker tracker(this);
    Fl_Widget_Tracker previousFocus(Fl::focus());
    take_focus();
    // No initial item: FLTK anchors the first row below the button, rather
    // than positioning the currently selected row over the button itself.
    const Fl_Menu_Item* item = menu()->pulldown(x(), y(), std::max(208,w()), h()+6, NULL, this);
    if (tracker.deleted()) return 1;
    if (item && !item->submenu()) {
      picked(item);
      if (!tracker.deleted()) redraw();
    }
    if (!tracker.deleted() && !previousFocus.deleted() && previousFocus.widget() != this)
      previousFocus.widget()->take_focus();
    return 1;
  }
};

#endif
