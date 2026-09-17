// Validation-only tone source. waveOut keeps the rendering stream owned by this process.
#include <windows.h>
#include <mmsystem.h>
#include <cmath>
#include <vector>
#pragma comment(lib, "winmm.lib")
int wmain(int argc, wchar_t** argv) {
    int seconds = argc > 1 ? _wtoi(argv[1]) : 12; const int rate=48000, frames=rate;
    std::vector<short> samples(frames*2); for(int i=0;i<frames;i++) { short v=(short)(9000*sin(2*3.141592653589793*440*i/rate)); samples[i*2]=samples[i*2+1]=v; }
    WAVEFORMATEX f{}; f.wFormatTag=WAVE_FORMAT_PCM; f.nChannels=2; f.nSamplesPerSec=rate; f.wBitsPerSample=16; f.nBlockAlign=4; f.nAvgBytesPerSec=rate*4;
    HWAVEOUT out; if(waveOutOpen(&out,WAVE_MAPPER,&f,0,0,CALLBACK_NULL)!=MMSYSERR_NOERROR) return 1;
    WAVEHDR h{}; h.lpData=(LPSTR)samples.data(); h.dwBufferLength=(DWORD)(samples.size()*sizeof(short));
    ULONGLONG until=GetTickCount64()+(ULONGLONG)seconds*1000; while(GetTickCount64()<until) { waveOutPrepareHeader(out,&h,sizeof(h)); waveOutWrite(out,&h,sizeof(h)); while(!(h.dwFlags&WHDR_DONE)) Sleep(10); waveOutUnprepareHeader(out,&h,sizeof(h)); }
    waveOutClose(out); return 0;
}
