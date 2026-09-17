#include <windows.h>
#include <mmdeviceapi.h>
#include <endpointvolume.h>
#include <cstdio>
int wmain(int argc,wchar_t**argv){if(argc!=2)return 2;BOOL target=!wcscmp(argv[1],L"on");CoInitializeEx(0,COINIT_MULTITHREADED);IMMDeviceEnumerator*e=0;IMMDevice*d=0;IAudioEndpointVolume*v=0;HRESULT h=CoCreateInstance(__uuidof(MMDeviceEnumerator),0,CLSCTX_ALL,IID_PPV_ARGS(&e));if(SUCCEEDED(h))h=e->GetDefaultAudioEndpoint(eRender,eCommunications,&d);if(SUCCEEDED(h))h=d->Activate(__uuidof(IAudioEndpointVolume),CLSCTX_ALL,0,(void**)&v);BOOL old=FALSE;if(SUCCEEDED(h)){v->GetMute(&old);h=v->SetMute(target,0);printf("{\"previousMute\":%s,\"currentMute\":%s,\"error\":%s}\n",old?"true":"false",target?"true":"false",SUCCEEDED(h)?"null":"\"SetMute failed\"");}if(v)v->Release();if(d)d->Release();if(e)e->Release();CoUninitialize();return FAILED(h);}
