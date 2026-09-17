// Small, self-contained process-loopback WAV recorder for Windows 10 2004+.
#define _WIN32_WINNT 0x0A00
#define NTDDI_VERSION 0x0A00000A // NTDDI_WIN10_FE (Windows 10, version 2004)
#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <audioclientactivationparams.h>
#include <propvarutil.h>
#include <cstdio>
#include <cwchar>
#include <string>
#include <vector>
#include <cmath>
#include <atomic>

struct Metrics {
    unsigned long long samples = 0;
    long double sumSquares = 0;
    int peak = 0;
    void add(const BYTE* data, UINT32 frames, UINT16 channels) {
        const short* p = reinterpret_cast<const short*>(data);
        unsigned long long count = static_cast<unsigned long long>(frames) * channels;
        for (unsigned long long i = 0; i < count; ++i) {
            int v = p[i]; int a = v < 0 ? -v : v;
            if (a > peak) peak = a;
            sumSquares += static_cast<long double>(v) * v;
        }
        samples += count;
    }
    double rms() const { return samples ? sqrt(static_cast<double>(sumSquares / samples)) : 0.0; }
};

static void put32(FILE* f, DWORD n) { fwrite(&n, 4, 1, f); }
static void put16(FILE* f, WORD n) { fwrite(&n, 2, 1, f); }

// Activation completes on an MTA worker.  IAgileObject prevents apartment marshaling.
class ActivationHandler final : public IActivateAudioInterfaceCompletionHandler, public IAgileObject {
public:
    std::atomic<ULONG> refs{1}; HANDLE done = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    HRESULT result = E_FAIL; IAudioClient* client = nullptr;
    ~ActivationHandler() { if (client) client->Release(); if (done) CloseHandle(done); }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** value) override {
        if (!value) return E_POINTER; *value = nullptr;
        if (iid == __uuidof(IUnknown) || iid == __uuidof(IActivateAudioInterfaceCompletionHandler)) {
            *value = static_cast<IActivateAudioInterfaceCompletionHandler*>(this); AddRef(); return S_OK;
        }
        if (iid == __uuidof(IAgileObject)) { *value = static_cast<IAgileObject*>(this); AddRef(); return S_OK; }
        return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++refs; }
    ULONG STDMETHODCALLTYPE Release() override { ULONG n = --refs; if (!n) delete this; return n; }
    HRESULT STDMETHODCALLTYPE ActivateCompleted(IActivateAudioInterfaceAsyncOperation* operation) override {
        IUnknown* unknown = nullptr; HRESULT activation = E_FAIL;
        HRESULT hr = operation->GetActivateResult(&activation, &unknown);
        if (SUCCEEDED(hr) && SUCCEEDED(activation)) hr = unknown->QueryInterface(IID_PPV_ARGS(&client));
        if (unknown) unknown->Release();
        result = FAILED(hr) ? hr : activation;
        SetEvent(done); return S_OK;
    }
};

static std::string hexhr(HRESULT hr) { char b[16]; sprintf_s(b, "0x%08lX", static_cast<unsigned long>(hr)); return b; }
static std::string jsonEscape(const std::string& s) { std::string o; for(char c:s) { if(c=='\\' || c=='\"') {o+='\\';o+=c;} else if(c=='\n')o+="\\n"; else if(c=='\r')o+="\\r"; else o+=c; } return o; }
static void emit(DWORD pid, double duration, UINT32 rate, UINT16 channels, const Metrics& m, const std::string& error) {
    double rms=m.rms(); bool signal=error.empty() && m.samples && m.peak >= 100 && rms >= 20.0;
    printf("{\"pid\":%lu,\"duration\":%.3f,\"sampleRate\":%u,\"channels\":%u,\"samples\":%llu,\"rms\":%.3f,\"peak\":%d,\"signal\":%s,\"error\":%s}\n",
        pid,duration,rate,channels,m.samples,rms,m.peak,signal?"true":"false",error.empty()?"null":("\""+jsonEscape(error)+"\"").c_str());
}

int wmain(int argc, wchar_t** argv) {
    DWORD pid=0; double seconds=0; const wchar_t* wav=nullptr;
    for (int i=1;i<argc;i++) {
        if (!wcscmp(argv[i],L"--pid") && i+1<argc) pid=wcstoul(argv[++i],nullptr,10);
        else if (!wcscmp(argv[i],L"--seconds") && i+1<argc) seconds=wcstod(argv[++i],nullptr);
        else if (!wcscmp(argv[i],L"--wav") && i+1<argc) wav=argv[++i];
        else { Metrics m; emit(pid,seconds,0,0,m,"usage: --pid <PID> --seconds <duration> --wav <output.wav>"); return 2; }
    }
    Metrics metrics; UINT32 rate=0; UINT16 channels=0; std::string error;
    HRESULT hr=CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    bool comInitialized = SUCCEEDED(hr);
    if (!pid || seconds<=0 || !wav) error="invalid arguments";
    else if (FAILED(hr) && hr != RPC_E_CHANGED_MODE) error="CoInitializeEx " + hexhr(hr);
    IAudioClient* audio=nullptr; IAudioCaptureClient* capture=nullptr; HANDLE sampleEvent=nullptr; FILE* file=nullptr;
    if (error.empty()) {
        auto* handler=new ActivationHandler();
        AUDIOCLIENT_ACTIVATION_PARAMS params{};
        params.ActivationType=AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK;
        params.ProcessLoopbackParams.TargetProcessId=pid;
        params.ProcessLoopbackParams.ProcessLoopbackMode=PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE;
        PROPVARIANT prop{}; prop.vt=VT_BLOB; prop.blob.cbSize=sizeof(params); prop.blob.pBlobData=reinterpret_cast<BYTE*>(&params);
        IActivateAudioInterfaceAsyncOperation* op=nullptr;
        HRESULT ahr=ActivateAudioInterfaceAsync(VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,__uuidof(IAudioClient),&prop,handler,&op);
        if (FAILED(ahr)) error="ActivateAudioInterfaceAsync " + hexhr(ahr);
        else if (WaitForSingleObject(handler->done,15000)!=WAIT_OBJECT_0) error="ActivateAudioInterfaceAsync timed out";
        else if (FAILED(handler->result)) error="activation " + hexhr(handler->result);
        else { audio=handler->client; handler->client=nullptr; }
        if(op) op->Release(); handler->Release();
    }
    WAVEFORMATEX format{};
    if (error.empty()) {
        // Asking shared mode to convert to this plain PCM format keeps WAV writing dependency-free.
        format.wFormatTag=WAVE_FORMAT_PCM; format.nChannels=2; format.nSamplesPerSec=48000;
        format.wBitsPerSample=16; format.nBlockAlign=4; format.nAvgBytesPerSec=192000;
        hr=audio->Initialize(AUDCLNT_SHAREMODE_SHARED,AUDCLNT_STREAMFLAGS_LOOPBACK|AUDCLNT_STREAMFLAGS_EVENTCALLBACK|AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM,0,0,&format,nullptr);
        if(FAILED(hr)) error="IAudioClient::Initialize " + hexhr(hr);
        else { rate=format.nSamplesPerSec; channels=format.nChannels; hr=audio->GetService(IID_PPV_ARGS(&capture)); if(FAILED(hr)) error="IAudioClient::GetService " + hexhr(hr); }
    }
    if (error.empty()) { sampleEvent=CreateEventW(nullptr,FALSE,FALSE,nullptr); if(!sampleEvent) error="CreateEvent failed"; else { hr=audio->SetEventHandle(sampleEvent); if(FAILED(hr)) error="IAudioClient::SetEventHandle "+hexhr(hr); } }
    if (error.empty() && _wfopen_s(&file,wav,L"wb")!=0) error="cannot open WAV output";
    if (error.empty()) {
        fwrite("RIFF",1,4,file); put32(file,0); fwrite("WAVEfmt ",1,8,file); put32(file,16); put16(file,1); put16(file,channels); put32(file,rate); put32(file,rate*channels*2); put16(file,channels*2); put16(file,16); fwrite("data",1,4,file); put32(file,0);
        hr=audio->Start(); if(FAILED(hr)) error="IAudioClient::Start "+hexhr(hr);
    }
    ULONGLONG end=GetTickCount64()+static_cast<ULONGLONG>(seconds*1000.0);
    while(error.empty() && GetTickCount64()<end) {
        ULONGLONG remaining=end-GetTickCount64();
        DWORD wait=static_cast<DWORD>(remaining < 100 ? remaining : 100);
        if(WaitForSingleObject(sampleEvent,wait)!=WAIT_OBJECT_0) continue;
        UINT32 packet=0;
        while(SUCCEEDED(capture->GetNextPacketSize(&packet)) && packet) {
            BYTE* data=nullptr; UINT32 frames=0; DWORD flags=0; hr=capture->GetBuffer(&data,&frames,&flags,nullptr,nullptr);
            if(FAILED(hr)) { error="IAudioCaptureClient::GetBuffer "+hexhr(hr); break; }
            size_t bytes=static_cast<size_t>(frames)*format.nBlockAlign;
            if(flags&AUDCLNT_BUFFERFLAGS_SILENT) { std::vector<BYTE> zero(bytes); fwrite(zero.data(),1,bytes,file); }
            else { fwrite(data,1,bytes,file); metrics.add(data,frames,channels); }
            if(flags&AUDCLNT_BUFFERFLAGS_SILENT) metrics.samples+=static_cast<unsigned long long>(frames)*channels;
            capture->ReleaseBuffer(frames); packet=0;
        }
    }
    if(audio) audio->Stop();
    if(file) { DWORD bytes=static_cast<DWORD>(metrics.samples/channels*format.nBlockAlign); fseek(file,4,SEEK_SET); put32(file,36+bytes); fseek(file,40,SEEK_SET); put32(file,bytes); fclose(file); }
    if(sampleEvent) CloseHandle(sampleEvent); if(capture) capture->Release(); if(audio) audio->Release(); if(comInitialized) CoUninitialize();
    emit(pid,seconds,rate,channels,metrics,error); return error.empty()?0:1;
}
