#include "../vendor/tigervnc/vncviewer/StyledMessage.h"
#include <cassert>
#include <iostream>

static int action;
static void dismiss(void*) {
  Fl_Window* window = Fl::first_window();
  assert(window && window->w() == 640);
  Window parent = vncMessageParent(), child;
  XWindowAttributes attributes;
  int px, py, dx, dy;
  assert(XGetWindowAttributes(fl_display, parent, &attributes));
  XTranslateCoordinates(fl_display, parent, attributes.root, 0, 0, &px, &py, &child);
  XTranslateCoordinates(fl_display, fl_xid(window), attributes.root, 0, 0, &dx, &dy, &child);
  assert(abs((dx + window->w()/2) - (px + attributes.width/2)) <= 2);
  assert(abs((dy + window->h()/2) - (py + attributes.height/2)) <= 2);
  if (action < 0) { window->do_callback(); return; }
  for (int i = 0; i < window->children(); ++i) {
    Fl_Button* button = dynamic_cast<Fl_Button*>(window->child(i));
    if (!button) continue;
    VncMessageAction* context = static_cast<VncMessageAction*>(button->user_data());
    if (context->index == action) {
      assert(button->box() == macBox());
      button->do_callback();
      return;
    }
  }
  assert(false);
}
int main() {
  Fl_Window parent(80, 120, 900, 500, "Launcher placement fixture");
  parent.show();
  Fl::wait(0.1);
  char id[32];
  snprintf(id, sizeof(id), "%lu", fl_xid(&parent));
  setenv("VNCMING_PARENT_WINDOW", id, 1);
  Fl::set_font(FL_HELVETICA, "Noto Sans CJK SC");
  Fl::set_font(FL_HELVETICA_BOLD, "Noto Sans CJK SC");
  for (int index : {0, 1, 2, -1}) {
    action = index;
    vncMessageTitle("证书确认 — VNCMing");
    Fl::add_timeout(0.3, dismiss);
    assert(vncChoice("%s", "取消", "继续", "返回", "测试证书确认的按钮结果，关闭窗口应取消。") == index);
  }
  action = 0;
  Fl::add_timeout(0.3, dismiss);
  vncAlert("连接失败：%s", "127.0.0.1");
  assert(vncMessageTitleStorage().empty());
  std::cout << "Styled message choices, cancellation and error dismissal passed\n";
}
