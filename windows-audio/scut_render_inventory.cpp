// Render-side Core Audio snapshotter. It deliberately never inspects capture devices.
#include <windows.h>
#include <mmdeviceapi.h>
#include <audiopolicy.h>
#include <functiondiscoverykeys_devpkey.h>
#include <appmodel.h>
#include <cstdio>
#include <string>
#include <vector>

static std::string utf8(const wchar_t* value) {
    if (!value) return "";
    int bytes = WideCharToMultiByte(CP_UTF8, 0, value, -1, nullptr, 0, nullptr, nullptr);
    std::string result(bytes, '\0');
    if (bytes) { WideCharToMultiByte(CP_UTF8, 0, value, -1, result.data(), bytes, nullptr, nullptr); result.pop_back(); }
    return result;
}
static std::string esc(const std::string& value) { std::string out; for(char c:value) { if(c=='\\'||c=='\"'){out+='\\';out+=c;} else if(c=='\n')out+="\\n"; else if(c=='\r')out+="\\r"; else if((unsigned char)c<32) out+=' '; else out+=c; } return out; }
static const char* stateName(DWORD state) { if(state==DEVICE_STATE_ACTIVE)return "ACTIVE"; if(state==DEVICE_STATE_DISABLED)return "DISABLED"; if(state==DEVICE_STATE_NOTPRESENT)return "NOTPRESENT"; if(state==DEVICE_STATE_UNPLUGGED)return "UNPLUGGED"; return "UNKNOWN"; }
static const char* sessionState(AudioSessionState state) { return state==AudioSessionStateActive?"ACTIVE":state==AudioSessionStateInactive?"INACTIVE":"EXPIRED"; }
static std::string processImage(DWORD pid) { if(!pid) return ""; HANDLE h=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid); if(!h)return ""; wchar_t path[32768]; DWORD size=32768; BOOL ok=QueryFullProcessImageNameW(h,0,path,&size); CloseHandle(h); return ok?utf8(path):""; }
static std::string packageIdentity(DWORD pid) { if(!pid)return ""; HANDLE h=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid); if(!h)return ""; UINT32 length=0; LONG rc=GetPackageFullName(h,&length,nullptr); std::wstring value(length,L'\0'); if(rc==ERROR_INSUFFICIENT_BUFFER) rc=GetPackageFullName(h,&length,value.data()); CloseHandle(h); return rc==ERROR_SUCCESS?utf8(value.c_str()):""; }
static void emitString(FILE* out, const char* name, const std::string& value) { fprintf(out,"\"%s\":\"%s\"",name,esc(value).c_str()); }

int wmain(int argc, wchar_t** argv) {
    FILE* out=stdout; if(argc==3 && !wcscmp(argv[1],L"--out")) _wfopen_s(&out,argv[2],L"wb");
    HRESULT hr=CoInitializeEx(nullptr,COINIT_MULTITHREADED); if(FAILED(hr)){fprintf(out,"{\"error\":\"CoInitializeEx\"}");return 1;}
    IMMDeviceEnumerator* devices=nullptr; hr=CoCreateInstance(__uuidof(MMDeviceEnumerator),nullptr,CLSCTX_ALL,IID_PPV_ARGS(&devices));
    if(FAILED(hr)){fprintf(out,"{\"error\":\"MMDeviceEnumerator\"}");CoUninitialize();return 1;}
    IMMDeviceCollection* collection=nullptr; devices->EnumAudioEndpoints(eRender,DEVICE_STATEMASK_ALL,&collection); UINT count=0; if(collection)collection->GetCount(&count);
    fprintf(out,"{\"kind\":\"render-core-audio-snapshot\",\"endpoints\":[");
    for(UINT i=0;i<count;i++) {
        IMMDevice* device=nullptr; collection->Item(i,&device); if(!device)continue;
        LPWSTR id=nullptr; device->GetId(&id); DWORD state=0; device->GetState(&state);
        IPropertyStore* store=nullptr; PROPVARIANT name; PropVariantInit(&name); std::string friendly;
        if(SUCCEEDED(device->OpenPropertyStore(STGM_READ,&store))) { if(SUCCEEDED(store->GetValue(PKEY_Device_FriendlyName,&name)) && name.vt==VT_LPWSTR) friendly=utf8(name.pwszVal); store->Release(); } PropVariantClear(&name);
        fprintf(out,"%s{",i?",":""); emitString(out,"endpointName",friendly); fprintf(out,","); emitString(out,"endpointId",utf8(id)); fprintf(out,",\"endpointState\":\"%s\",\"sessions\":[",stateName(state));
        IAudioSessionManager2* manager=nullptr; HRESULT activate=device->Activate(__uuidof(IAudioSessionManager2),CLSCTX_ALL,nullptr,(void**)&manager);
        IAudioSessionEnumerator* sessions=nullptr; int sessionCount=0; if(SUCCEEDED(activate) && SUCCEEDED(manager->GetSessionEnumerator(&sessions))) sessions->GetCount(&sessionCount);
        for(int j=0;j<sessionCount;j++) {
            IAudioSessionControl* control=nullptr; sessions->GetSession(j,&control); IAudioSessionControl2* control2=nullptr; if(!control || FAILED(control->QueryInterface(IID_PPV_ARGS(&control2)))){if(control)control->Release();continue;}
            LPWSTR identifier=nullptr, display=nullptr; control2->GetSessionIdentifier(&identifier); control->GetDisplayName(&display); DWORD pid=0; control2->GetProcessId(&pid); AudioSessionState ss; control->GetState(&ss);
            fprintf(out,"%s{",j?",":""); emitString(out,"sessionIdentifier",utf8(identifier)); fprintf(out,","); emitString(out,"displayName",utf8(display)); fprintf(out,",\"pid\":%lu,",pid); emitString(out,"processExecutable",processImage(pid)); fprintf(out,","); emitString(out,"packageIdentity",packageIdentity(pid)); fprintf(out,",\"sessionState\":\"%s\"}",sessionState(ss));
            if(identifier)CoTaskMemFree(identifier); if(display)CoTaskMemFree(display); control2->Release(); control->Release();
        }
        fprintf(out,"]}"); if(sessions)sessions->Release(); if(manager)manager->Release(); if(id)CoTaskMemFree(id); device->Release();
    }
    fprintf(out,"]}\n"); if(collection)collection->Release(); devices->Release(); CoUninitialize(); if(out!=stdout)fclose(out); return 0;
}
