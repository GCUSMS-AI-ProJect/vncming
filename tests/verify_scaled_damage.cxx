// Validate partial bilinear rendering against full rendering on real XRender surfaces.
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <FL/Fl_RGB_Image.H>
#include <FL/x.H>
#include "Surface.h"
#include "ScaledDamage.h"

class TestSurface : public Surface {
public:
  TestSurface(int w, int h) : Surface(w,h) {}
  TestSurface(Fl_RGB_Image* image) : Surface(image) {}
  using Surface::update;
  std::vector<unsigned long> pixels() {
    XImage* image=XGetImage(fl_display,pixmap,0,0,width(),height(),AllPlanes,ZPixmap);
    if (!image) std::abort();
    std::vector<unsigned long> result(width()*height());
    for(int y=0;y<height();++y) for(int x=0;x<width();++x)
      result[y*width()+x]=XGetPixel(image,x,y);
    XDestroyImage(image);
    return result;
  }
};

static void require(bool ok, const char* message) {
  if (!ok) { std::fprintf(stderr,"FAIL: %s\n",message); std::exit(1); }
}

static void check(int sw,int sh,int tw,int th) {
  std::vector<unsigned char> data(sw*sh*4);
  for(int i=0;i<sw*sh;++i) {
    data[i*4]=i%251;data[i*4+1]=(i/7)%253;data[i*4+2]=(i/11)%255;data[i*4+3]=255;
  }
  Fl_RGB_Image image(data.data(),sw,sh,4);
  TestSurface source(&image), full(tw+24,th+18), partial(tw+24,th+18);
  full.clear(12,24,36);partial.clear(12,24,36);
  source.drawScaled(&full,11,7,tw,th);
  source.drawScaled(&partial,11,7,tw,th);
  require(full.pixels()==partial.pixels(),"initial image differs");
  for(int step=0;step<28;++step) {
    int left=step<4?(step%2?sw-1:0):(step*137)%sw;
    int top=step<4?(step/2?sh-1:0):(step*83)%sh;
    int right=std::min(sw,left+1+step%37),bottom=std::min(sh,top+1+step%29);
    for(int y=top;y<bottom;++y) for(int x=left;x<right;++x) {
      data[(y*sw+x)*4]=(step*31+17)%255;
      data[(y*sw+x)*4+1]=(step*19+31)%255;
      data[(y*sw+x)*4+2]=(step*47+73)%255;
    }
    source.update(&image);
    rfb::Rect clip=scaledDamage(rfb::Rect(left,top,right,bottom),sw,sh,tw,th);
    auto before=partial.pixels();
    source.drawScaled(&full,11,7,tw,th);
    source.drawScaled(&partial,11,7,tw,th,clip.tl.x+11,clip.tl.y+7,clip.width(),clip.height());
    auto expected=full.pixels(), actual=partial.pixels();
    for(size_t i=0;i<expected.size();++i) {
      int x=i%(tw+24),y=i/(tw+24);
      bool inside=clip.translate(rfb::Point(11,7)).contains(rfb::Point(x,y));
      if(!inside) require(before[i]==actual[i],"pixel outside damage changed");
      // Pixman starts fixed-point sampling at the clipped boundary, which
      // can change bilinear rounding by one channel value at fractional scales.
      for(int shift=0;shift<32;shift+=8)
        require(std::abs(int((expected[i]>>shift)&255)-int((actual[i]>>shift)&255))<=1,
                "incremental image differs by more than one channel value");
    }
  }
  // Unscaled drawing must work after the scaled picture transform is restored.
  TestSurface direct(sw,sh);
  source.draw(&direct,0,0,0,0,sw,sh);
  require(source.pixels()==direct.pixels(),"scale transform leaked into unscaled rendering");
  std::printf("pixel comparison (channel tolerance 1): %dx%d -> %dx%d, 28 updates, edges and offsets\n",sw,sh,tw,th);
}

static double benchmark(bool incremental) {
  TestSurface source(1920,1080), target(1280,720);
  source.clear(30,60,120);
  const rfb::Rect clip=scaledDamage(rfb::Rect(960,540,992,572),1920,1080,1280,720);
  XSync(fl_display,False);
  auto begin=std::chrono::steady_clock::now();
  for(int i=0;i<300;++i) {
    if(incremental) source.drawScaled(&target,0,0,1280,720,clip.tl.x,clip.tl.y,clip.width(),clip.height());
    else source.drawScaled(&target,0,0,1280,720);
  }
  auto completed=target.pixels();
  require(!completed.empty(),"benchmark readback");
  XSync(fl_display,False);
  return std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
}

int main() {
  require(scaledDamage(rfb::Rect(0,0,0,0),800,600,400,300).is_empty(),"empty damage");
  require(scaledDamage(rfb::Rect(0,0,10,10),800,600,0,0).is_empty(),"zero viewport");
  check(800,600,400,300);check(320,240,800,600);check(647,481,503,379);
  check(800,600,800,600);check(1920,1080,1280,720);check(1,1,128,96);
  std::vector<double> full,partial;
  for(int i=0;i<5;++i) {
    if(i%2) {partial.push_back(benchmark(true));full.push_back(benchmark(false));}
    else {full.push_back(benchmark(false));partial.push_back(benchmark(true));}
  }
  std::sort(full.begin(),full.end());std::sort(partial.begin(),partial.end());
  rfb::Rect clip=scaledDamage(rfb::Rect(960,540,992,572),1920,1080,1280,720);
  std::printf("local XRender benchmark, 300 composites, median of 5: full=%.3fms partial=%.3fms; area=%d vs %d pixels\n",full[2],partial[2],1280*720,clip.area());
}
