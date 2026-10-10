#ifndef VNCMING_MAC_MOTION_H
#define VNCMING_MAC_MOTION_H
#include <FL/Fl.H>
#include <FL/Fl_Button.H>
#include <FL/Fl_Return_Button.H>
#include <FL/Fl_Window.H>
#include <FL/Fl_Input.H>
#include <FL/Fl_Secret_Input.H>
#include <FL/Fl_Int_Input.H>
#include <FL/Fl_Choice.H>
#include <FL/Fl_Tabs.H>
#include <FL/Fl_Check_Button.H>
#include <FL/fl_draw.H>
#include <FL/x.H>
#include <sys/time.h>
#include <algorithm>

inline double motionTime() {
  timeval tv; gettimeofday(&tv, 0);
  return tv.tv_sec + tv.tv_usec / 1000000.0;
}
inline void macRoundBox(int x, int y, int w, int h, Fl_Color c) {
  const int r = std::min(8, std::min(w, h) / 2);
  fl_color(c);
  fl_rectf(x+r, y, w-2*r, h);
  fl_rectf(x, y+r, w, h-2*r);
  fl_pie(x,y,2*r,2*r,90,180); fl_pie(x+w-2*r,y,2*r,2*r,0,90);
  fl_pie(x,y+h-2*r,2*r,2*r,180,270); fl_pie(x+w-2*r,y+h-2*r,2*r,2*r,270,360);
}
inline void modernBorderBox(int x, int y, int w, int h, Fl_Color c);
inline Fl_Boxtype macBox() {
  static bool ready=false;
  // MonitorArrangement uses FL_FREE_BOXTYPE for its required-screen pattern.
  const Fl_Boxtype b=static_cast<Fl_Boxtype>(FL_FREE_BOXTYPE + 8);
  if (!ready) { Fl::set_boxtype(b,modernBorderBox,8,4,16,8); ready=true; }
  return b;
}
inline void modernBorderBox(int x, int y, int w, int h, Fl_Color c) {
  macRoundBox(x, y, w, h, fl_rgb_color(221, 216, 210));
  if (w > 2 && h > 2) macRoundBox(x+1, y+1, w-2, h-2, c);
}
inline void modernInputBoxDraw(int x, int y, int w, int h, Fl_Color c) {
  Fl_Widget* focus = Fl::focus();
  bool focused = focus && focus->x() == x && focus->y() == y && focus->w() == w && focus->h() == h;
  macRoundBox(x, y, w, h, focused ? fl_rgb_color(245,155,89) : fl_rgb_color(221,216,210));
  if (w > 2 && h > 2) macRoundBox(x+1,y+1,w-2,h-2,c);
}
inline Fl_Boxtype modernInputBox() {
  static bool ready=false;
  Fl_Boxtype b=static_cast<Fl_Boxtype>(FL_FREE_BOXTYPE+9);
  if (!ready) { Fl::set_boxtype(b,modernInputBoxDraw,8,5,16,10);ready=true; }
  return b;
}
inline Fl_Boxtype modernPanelBox() {
  static bool ready=false;
  Fl_Boxtype b=static_cast<Fl_Boxtype>(FL_FREE_BOXTYPE+10);
  if (!ready) { Fl::set_boxtype(b,modernBorderBox,8,4,16,8);ready=true; }
  return b;
}
template<class Base> class ModernInputWidget : public Base {
public:
  ModernInputWidget(int x,int y,int w,int h,const char* label=0):Base(x,y,w,h,label) {
    this->box(modernInputBox());this->color(FL_WHITE);
    this->textcolor(fl_rgb_color(55,50,45));this->selection_color(fl_rgb_color(245,128,37));
    this->textsize(14);
  }
  int handle(int event) {
    int result=Base::handle(event);
    if(event==FL_FOCUS || event==FL_UNFOCUS) this->redraw();
    return result;
  }
};
typedef ModernInputWidget<Fl_Input> ModernInput;
typedef ModernInputWidget<Fl_Secret_Input> ModernSecretInput;
typedef ModernInputWidget<Fl_Int_Input> ModernIntInput;
class ModernCheckButton : public Fl_Check_Button {
public:
  ModernCheckButton(int x,int y,int w,int h,const char* label=0):Fl_Check_Button(x,y,w,h,label) {
    down_box(modernPanelBox());selection_color(fl_rgb_color(245,128,37));
    labelcolor(fl_rgb_color(81,74,67));
  }
};
class ModernChoice : public Fl_Choice {
public:
  ModernChoice(int x,int y,int w,int h,const char* label=0):Fl_Choice(x,y,w,h,label) {
    box(modernPanelBox());down_box(modernPanelBox());color(FL_WHITE);
    selection_color(fl_rgb_color(245,128,37));textsize(14);
  }
};
class ModernTabs : public Fl_Tabs {
  int headerHeight() { return children() ? child(0)->y()-y() : 28; }
public:
  ModernTabs(int x,int y,int w,int h):Fl_Tabs(x,y,w,h) { box(FL_FLAT_BOX); }
  void draw() {
    int height=headerHeight();
    fl_color(fl_rgb_color(246,245,243));fl_rectf(x(),y(),w(),h());
    fl_color(fl_rgb_color(225,220,214));fl_rectf(x(),y()+height-1,w(),1);
    Fl_Widget* selected=value();
    for(int i=0;i<children();++i) {
      int left=x()+i*w()/children(),right=x()+(i+1)*w()/children();
      bool active=child(i)==selected;
      if(active) {
        macRoundBox(left+2,y()+2,right-left-4,height-4,fl_rgb_color(255,236,219));
        fl_color(fl_rgb_color(245,128,37));fl_rectf(left+10,y()+height-2,right-left-20,2);
      }
      fl_color(active ? fl_rgb_color(164,77,20):fl_rgb_color(81,74,67));
      fl_font(active ? FL_HELVETICA_BOLD:FL_HELVETICA,12);
      fl_draw(child(i)->label(),left,y(),right-left,height,FL_ALIGN_CENTER);
    }
    if(selected) draw_child(*selected);
  }
  int handle(int event) {
    if(Fl::event_y()>=y() && Fl::event_y()<y()+headerHeight() &&
       Fl::event_x()>=x() && Fl::event_x()<x()+w() &&
       (event==FL_PUSH || event==FL_RELEASE || event==FL_DRAG)) {
      if(event==FL_RELEASE && children()) {
        int index=std::min(children()-1,(Fl::event_x()-x())*children()/w());
        value(child(index));set_changed();redraw();do_callback();
      }
      return 1;
    }
    return Fl_Tabs::handle(event);
  }
};
template<class Base> class MotionButton : public Base {
  Fl_Color rest, from, target;
  bool hovering, paletteReady;
  double began;
  static void tick(void *p) {
    MotionButton *b=static_cast<MotionButton*>(p);
    double t=std::min(1.0,(motionTime()-b->began)/0.16);
    t=1-(1-t)*(1-t)*(1-t);
    unsigned char r,g,bl,rr,gg,bb;
    Fl::get_color(b->from,r,g,bl); Fl::get_color(b->target,rr,gg,bb);
    b->color(fl_rgb_color(r+(rr-r)*t,g+(gg-g)*t,bl+(bb-bl)*t)); b->redraw();
    if(t<1) Fl::repeat_timeout(1.0/60,tick,p);
  }
  void animate(Fl_Color c) {
    Fl::remove_timeout(tick,this); from=this->color(); target=c; began=motionTime();
    Fl::add_timeout(0,tick,this);
  }
public:
  MotionButton(int x,int y,int w,int h,const char *s=0):Base(x,y,w,h,s),hovering(false),paletteReady(false) {
    this->box(macBox()); this->down_box(macBox());
    rest=from=target=this->color(); began=0;
  }
  ~MotionButton() { Fl::remove_timeout(tick,this); }
  int handle(int e) {
    if(!paletteReady && (e==FL_ENTER || e==FL_PUSH)) { rest=this->color(); paletteReady=true; }
    if(e==FL_ENTER) { hovering=true; animate(fl_color_average(rest,FL_WHITE,0.85f)); }
    if(e==FL_LEAVE) { hovering=false; animate(rest); }
    if(e==FL_PUSH) animate(fl_color_average(rest,FL_BLACK,0.88f));
    if(e==FL_RELEASE) animate(hovering?fl_color_average(rest,FL_WHITE,0.85f):rest);
    return Base::handle(e);
  }
};
typedef MotionButton<Fl_Button> MacButton;
class MacReturnButton : public MotionButton<Fl_Return_Button> {
public:
  MacReturnButton(int x,int y,int w,int h,const char* label=0)
    : MotionButton<Fl_Return_Button>(x,y,w,h,label) {}
  void draw() { Fl_Button::draw(); }
};

class MotionWindow : public Fl_Window {
  double began;
  bool closing;
  void opacity(double value) {
    if(!shown() || !fl_xid(this)) return;
    unsigned long alpha=static_cast<unsigned long>(0xffffffffUL*value);
    Atom atom=XInternAtom(fl_display,"_NET_WM_WINDOW_OPACITY",False);
    XChangeProperty(fl_display,fl_xid(this),atom,XA_CARDINAL,32,PropModeReplace,
                    reinterpret_cast<unsigned char*>(&alpha),1);
    XFlush(fl_display);
  }
  static void tick(void *p) {
    MotionWindow *w=static_cast<MotionWindow*>(p);
    double t=std::min(1.0,(motionTime()-w->began)/(w->closing?0.14:0.20));
    double ease=1-(1-t)*(1-t)*(1-t);
    w->opacity(w->closing?1-ease:ease);
    if(t<1) Fl::repeat_timeout(1.0/60,tick,p);
    else if(w->closing) { w->Fl_Window::hide(); w->closing=false; }
  }
public:
  MotionWindow(int w,int h,const char *s=0):Fl_Window(w,h,s),began(0),closing(false) {}
  ~MotionWindow() { Fl::remove_timeout(tick,this); }
  void show() {
    if(shown() && !closing) { Fl_Window::show(); return; }
    Fl::remove_timeout(tick,this); closing=false; Fl_Window::show(); opacity(0);
    began=motionTime(); Fl::add_timeout(0,tick,this);
  }
  void hide() {
    // Authentication must leave its nested event loop immediately; keeping
    // it alive during a closing animation can re-enter the RFB decoder.
    Fl::remove_timeout(tick,this); closing=false; Fl_Window::hide();
  }
};
#endif
