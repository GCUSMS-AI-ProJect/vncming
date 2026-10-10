#include "../vendor/tigervnc/vncviewer/StyledMessage.h"
#include <cassert>
#include <iostream>

static int action;
static void dismiss(void*) {
  Fl_Window* window = Fl::first_window();
  assert(window && window->w() == 640);
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
