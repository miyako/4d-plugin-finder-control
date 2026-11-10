#import <AppKit/AppKit.h>
#include "4DPlugin-Finder-Control.h"
#include "4DPlugin-JSON.h"
#include "PrivateTypes.h"
#include "EntryPoints.h"
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>

using Text = std::basic_string<PA_Unichar>;
static void require(bool condition, const char *message) {
    if(!condition) throw std::runtime_error(message);
}
static Text text(const char16_t *value) {
    return Text(reinterpret_cast<const PA_Unichar *>(value));
}
static std::set<PA_Unichar *> strings;
static std::map<PA_Handle, size_t> handles;
struct Ref {
    int owners = 1;
    std::map<Text, PA_Variable> properties;
};
static std::set<Ref *> refs;
static std::set<PA_Picture> pictures;
static bool nullEmpty = false;
static bool failGetter = false;
static PA_Variable poisonedOutput;
static int failHandleAfter = -1;
static int stringifyMode = 0;
static int permissionCalls = 0;
static int applicationCalls = 0;
static int revealCalls = 0;
static int deleteCalls = 0;
static NSString *fixtureComment = nil;
static bool fixtureLocked = false;
static bool fixtureHidden = false;

@implementation SBObject
- (BOOL)exists { return YES; }
@end
@interface AuditItem : SBObject
@end
@implementation AuditItem
- (NSString *)comment { return fixtureComment; }
- (void)setComment:(NSString *)value {
    [fixtureComment release];
    fixtureComment = [value copy];
}
- (BOOL)locked { return fixtureLocked; }
- (void)setLocked:(BOOL)value { fixtureLocked = value; }
- (BOOL)extensionHidden { return fixtureHidden; }
- (void)setExtensionHidden:(BOOL)value { fixtureHidden = value; }
- (NSString *)displayedName { return @"Name \u65e5\U0001f600"; }
- (NSString *)objectDescription { return @"Description \u65e5\U0001f600"; }
- (NSString *)kind { return @"Kind \u65e5\U0001f600"; }
- (void)reveal { ++revealCalls; }
- (id)delete { ++deleteCalls; return nil; }
@end
@implementation SBElementArray
- (id)objectAtLocation:(id)location {
    require([location isKindOfClass:[NSURL class]], "synthetic path must become URL");
    return [[[AuditItem alloc] init] autorelease];
}
@end
@implementation SBApplication
+ (id)applicationWithBundleIdentifier:(NSString *)identifier {
    require([identifier isEqualToString:@"com.apple.Finder"], "unexpected application");
    ++applicationCalls;
    return [[[SBApplication alloc] init] autorelease];
}
- (SBElementArray *)items { return [[[SBElementArray alloc] init] autorelease]; }
@end

// Strong executable definitions prevent any real AppleEvent/permission request.
OSErr AECreateDesc(DescType type, const void *bytes, Size length, AEDesc *desc) {
    require(type == typeApplicationBundleID, "unexpected address descriptor");
    require(std::string(static_cast<const char *>(bytes), length) == "com.apple.Finder",
            "unexpected permission target");
    *desc = {};
    ++permissionCalls;
    return noErr;
}
OSStatus AEDeterminePermissionToAutomateTarget(const AEAddressDesc *, AEEventClass,
                                              AEEventID, Boolean) {
    ++permissionCalls;
    return errAEEventNotPermitted;
}
OSErr AEDisposeDesc(AEDesc *) { ++permissionCalls; return noErr; }

static PA_Unistring makeString(const Text &value) {
    PA_Unistring result{};
    if(value.empty() && nullEmpty) return result;
    result.fString = static_cast<PA_Unichar *>(std::malloc((value.size() + 1) * sizeof(PA_Unichar)));
    require(result.fString != nullptr, "fixture string allocation");
    require(strings.insert(static_cast<PA_Unichar *>(result.fString)).second, "duplicate string allocation");
    std::memcpy(result.fString, value.c_str(), (value.size() + 1) * sizeof(PA_Unichar));
    result.fLength = static_cast<PA_long32>(value.size());
    return result;
}
static Text readString(PA_Unistring value) {
    if(!value.fString) {
        require(value.fLength == 0, "null nonempty string");
        return {};
    }
    require(strings.count(static_cast<PA_Unichar *>(value.fString)), "read of disposed/unowned string");
    require(value.fString[value.fLength] == 0, "missing UTF-16 terminator");
    return Text(value.fString, value.fLength);
}
static void disposeString(PA_Unistring value) {
    if(!value.fString) {
        require(value.fLength == 0, "invalid null string disposal");
        return;
    }
    require(strings.erase(static_cast<PA_Unichar *>(value.fString)) == 1, "double/borrowed string disposal");
    std::free(value.fString);
}
static Ref *newRef() {
    Ref *result = new Ref;
    refs.insert(result);
    return result;
}
static Ref *reference(void *value) {
    auto result = static_cast<Ref *>(value);
    require(refs.count(result), "invalid/disposed object or collection");
    return result;
}
static void clear(PA_Variable *);
static void releaseRef(void *value) {
    if(!value) return;
    Ref *ref = reference(value);
    if(--ref->owners == 0) {
        for(auto &entry : ref->properties) clear(&entry.second);
        refs.erase(ref);
        delete ref;
    }
}
static PA_Variable copyVariable(PA_Variable value) {
    if(value.fType == eVK_Unistring)
        value.uValue.fString = makeString(readString(value.uValue.fString));
    else if(value.fType == eVK_Object && value.uValue.fObject)
        ++reference(value.uValue.fObject)->owners;
    else if(value.fType == eVK_Collection && value.uValue.fCollection)
        ++reference(value.uValue.fCollection)->owners;
    else if(value.fType == eVK_Picture && value.uValue.fPicture) {
        auto picture = std::malloc(1);
        pictures.insert(picture);
        value.uValue.fPicture = picture;
    }
    return value;
}
static void clear(PA_Variable *value) {
    switch(static_cast<unsigned char>(value->fType)) {
        case eVK_Unistring: disposeString(value->uValue.fString); break;
        case eVK_Object: releaseRef(value->uValue.fObject); break;
        case eVK_Collection: releaseRef(value->uValue.fCollection); break;
        case eVK_Picture:
            if(value->uValue.fPicture) {
                require(pictures.erase(static_cast<void *>(value->uValue.fPicture)), "invalid picture disposal");
                std::free(value->uValue.fPicture);
            }
            break;
        case eVK_ArrayUnicode: {
            PA_Handle handle = value->uValue.fArray.fData;
            require(handles.count(handle), "invalid array handle");
            auto elements = reinterpret_cast<PA_Unistring *>(*handle);
            for(int i = 0; i <= value->uValue.fArray.fNbElements; ++i)
                disposeString(elements[i]);
            PA_DisposeHandle(handle);
            break;
        }
        case eVK_Undefined: case eVK_Real: case eVK_Boolean: case eVK_Longint:
        case eVK_Null: break;
        default: throw std::runtime_error("invalid/raw-kind-0 variable cleanup");
    }
    *value = {};
    value->fType = eVK_Undefined;
}

static void engine(short selector, EngineBlock *eb) {
    switch(selector) {
        case EX_CREATE_UNISTRING:
            eb->fUniString1 = makeString(eb->fHandle ?
                Text(reinterpret_cast<PA_Unichar *>(eb->fHandle)) : Text());
            break;
        case EX_SET_UNISTRING: {
            // Copy input before releasing the old owner, as a content setter does.
            Text input(reinterpret_cast<PA_Unichar *>(eb->fHandle));
            disposeString(eb->fUniString1);
            eb->fUniString1 = makeString(input);
            break;
        }
        case EX_DISPOSE_UNISTRING: disposeString(eb->fUniString1); break;
        case EX_VARIABLE_TO_STRING: {
            auto value = reinterpret_cast<PA_Variable *>(eb->fHandle);
            require(value->fType == eVK_Unistring, "raw-kind-0/nonstring read");
            readString(value->uValue.fString);
            eb->fUniString1 = value->uValue.fString;
            break;
        }
        case EX_CLEAR_VARIABLE: clear(static_cast<PA_Variable *>(eb->fPtr1)); break;
        case EX_HANDLE_MANAGER: {
            PA_Handle handle = eb->fHandle;
            switch(eb->fParam1) {
                case 1:
                    if(failHandleAfter == 0) {
                        failHandleAfter = -1;
                        eb->fHandle = nullptr;
                        eb->fError = eER_NotEnoughMemory;
                        return;
                    }
                    if(failHandleAfter > 0) --failHandleAfter;
                    handle = static_cast<PA_Handle>(std::malloc(sizeof(char *)));
                    *handle = static_cast<char *>(std::calloc(1, eb->fParam2 > 0 ? eb->fParam2 : 1));
                    require(*handle != nullptr, "fixture handle allocation");
                    handles[handle] = eb->fParam2;
                    eb->fHandle = handle;
                    break;
                case 2:
                    require(handles.erase(handle), "invalid handle disposal");
                    std::free(*handle);
                    std::free(handle);
                    break;
                case 3:
                    require(handles.count(handle), "invalid handle resize");
                    *handle = static_cast<char *>(std::realloc(*handle, eb->fParam2));
                    require(*handle != nullptr, "fixture handle reallocation");
                    handles[handle] = eb->fParam2;
                    break;
                case 4:
                    require(handles.count(handle), "invalid handle size");
                    eb->fParam2 = handles.at(handle);
                    break;
                case 5:
                    if(!handle) {
                        eb->fParam3 = 0;
                        eb->fError = eER_NotEnoughMemory;
                        return;
                    }
                    require(handles.count(handle), "invalid handle lock");
                    eb->fParam3 = reinterpret_cast<sLONG_PTR>(*handle);
                    break;
                case 6:
                    if(handle) require(handles.count(handle), "invalid handle unlock");
                    break;
                default: throw std::runtime_error("unexpected handle operation");
            }
            break;
        }
        case EX_CREATE_PICTURE:
            eb->fPicture = std::malloc(1);
            pictures.insert(static_cast<void *>(eb->fPicture));
            break;
        case EX_GET_OBJ_VALUE: {
            auto output = static_cast<PA_Variable *>(eb->fPtr2);
            if(failGetter) {
                // Deliberately invalid-for-adoption output; error must win over its bytes.
                *output = poisonedOutput;
                eb->fError = eER_NotEnoughMemory;
                return;
            }
            auto ref = reference(eb->fPtr1);
            *output = copyVariable(ref->properties.at(readString(eb->fUniString1)));
            break;
        }
        case EX_SET_OBJ_VALUE: {
            auto ref = reference(eb->fPtr1);
            Text key = readString(eb->fUniString1);
            auto found = ref->properties.find(key);
            if(found != ref->properties.end()) clear(&found->second);
            ref->properties[key] = copyVariable(*static_cast<PA_Variable *>(eb->fPtr2));
            break;
        }
        case EX_EXECUTE_COMMAND_BY_ID: {
            auto args = static_cast<PA_Variable **>(eb->fPtr1);
            auto output = static_cast<PA_Variable *>(eb->fPtr2);
            if(eb->fParam1 == 1231) {
                auto ref = reference(PA_GetObjectVariable(*args[0]));
                PA_SetBooleanVariable(output, ref->properties.count(readString(args[1]->uValue.fString)));
            } else if(eb->fParam1 == 1225) {
                auto original = reference(PA_GetObjectVariable(*args[0]));
                auto duplicate = newRef();
                for(auto &entry : original->properties)
                    duplicate->properties[entry.first] = copyVariable(entry.second);
                PA_SetObjectVariable(output, duplicate);
            } else if(eb->fParam1 == 1217) {
                reference(PA_GetObjectVariable(*args[0]));
                if(stringifyMode == 1) {
                    eb->fError = eER_NotEnoughMemory;
                    return;
                }
                if(stringifyMode == 2) {
                    PA_SetObjectVariable(output, newRef());
                    return;
                }
                PA_Unistring string = makeString(text(u"{\"x\":\"\u65e5\U0001f600\"}"));
                PA_SetStringVariable(output, &string);
            } else throw std::runtime_error("unexpected SDK command");
            break;
        }
        default: throw std::runtime_error("unexpected engine selector");
    }
}

static PA_ObjectRef objectWith(PA_Variable value) {
    auto ref = newRef();
    ref->properties[text(u"key")] = copyVariable(value);
    return ref;
}
static void balanced() {
    require(strings.empty(), "outstanding string owners");
    require(handles.empty(), "outstanding handles");
    require(refs.empty(), "outstanding object/collection references");
    require(pictures.empty(), "outstanding picture owners");
}
static void testSetters() {
    auto obj = newRef();
    const wchar_t *wide = L"ASCII \u65e5\U0001f600";
    const char *utf8 = "ASCII \xe6\x97\xa5\xf0\x9f\x98\x80";
    Text expected = text(u"ASCII \u65e5\U0001f600");
    for(int repeat = 0; repeat != 4; ++repeat) {
        ob_set_s(obj, "narrow", utf8);
        ob_set_s(obj, L"wide", utf8);
        ob_set_a(obj, L"wchar", wide);
        ob_set_a(obj, L"utf16", &expected);
        for(auto &entry : obj->properties)
            require(readString(entry.second.uValue.fString) == expected, "setter exact UTF-16");
        ob_set_s(obj, "narrow", "");
        ob_set_s(obj, L"wide", "");
        ob_set_a(obj, L"wchar", L"");
        Text empty;
        ob_set_a(obj, L"utf16", &empty);
        for(auto &entry : obj->properties)
            require(readString(entry.second.uValue.fString).empty(), "setter empty");
    }
    PA_DisposeObject(obj);
    balanced();
}
static void testPicture() {
    auto obj = newRef();
    PA_Picture picture = PA_CreatePicture(nullptr, 0);
    ob_set_p(obj, L"picture", picture); // Existing setter consumes this owner.
    require(pictures.size() >= 1, "property picture must survive input cleanup");
    PA_DisposeObject(obj);
    balanced();
}
static void testGetters() {
    const std::pair<const char16_t *, const char *> fixtures[] = {
        {u"ASCII", "ASCII"}, {u"\u65e5", "\xe6\x97\xa5"},
        {u"\U0001f600", "\xf0\x9f\x98\x80"}, {u"", ""}
    };
    for(auto fixture : fixtures) {
        PA_Variable input{};
        auto string = makeString(text(fixture.first));
        PA_SetStringVariable(&input, &string);
        auto obj = objectWith(input);
        PA_ClearVariable(&input);
        for(int repeat = 0; repeat != 5; ++repeat) {
            CUTF8String result;
            require(ob_get_a(obj, L"key", &result), "existing string property");
            CUTF8String bytes(reinterpret_cast<const uint8_t *>(fixture.second));
            require(result == bytes, "getter exact UTF-8 bytes");
            require(!ob_get_b(obj, L"key"), "boolean string mismatch");
            require(ob_get_n(obj, L"key") == 0, "real string mismatch");
            require(!ob_get_o(obj, L"key"), "object string mismatch");
            require(!ob_get_c(obj, L"key"), "collection string mismatch");
        }
        PA_DisposeObject(obj);
    }
    for(int kind : {eVK_Boolean, eVK_Real}) {
        PA_Variable input{};
        if(kind == eVK_Boolean) PA_SetBooleanVariable(&input, true);
        else PA_SetRealVariable(&input, 42.5);
        auto obj = objectWith(input);
        if(kind == eVK_Boolean) require(ob_get_b(obj, L"key"), "boolean value");
        else require(ob_get_n(obj, L"key") == 42.5, "real value");
        PA_DisposeObject(obj);
    }
    balanced();
}
static void testHandoffs() {
    for(bool collection : {false, true}) {
        Ref *child = newRef();
        PA_Variable input{};
        if(collection) PA_SetCollectionVariable(&input, child);
        else PA_SetObjectVariable(&input, child);
        auto obj = objectWith(input);
        PA_ClearVariable(&input);
        CUTF8String ignored;
        ob_get_a(obj, L"key", &ignored);
        ob_get_b(obj, L"key");
        ob_get_n(obj, L"key");
        if(collection) require(!ob_get_o(obj, L"key"), "object collection mismatch");
        else require(!ob_get_c(obj, L"key"), "collection object mismatch");
        void *owned = collection ? ob_get_c(obj, L"key") : ob_get_o(obj, L"key");
        require(owned == child, "successful owning getter handoff");
        PA_DisposeObject(obj);
        require(reference(owned)->owners == 1, "handoff survives parent cleanup without leaked refs");
        if(collection) PA_DisposeCollection(owned);
        else PA_DisposeObject(owned);
    }
    balanced();
}
static void testFailedGetter(int kind) {
    PA_Variable input{};
    PA_SetBooleanVariable(&input, false);
    auto obj = objectWith(input);
    failGetter = true;
    poisonedOutput = {};
    CUTF8String output(reinterpret_cast<const uint8_t *>("unchanged"));
    switch(kind) {
        case eVK_Unistring:
            poisonedOutput.fType = eVK_Unistring;
            poisonedOutput.uValue.fString.fString = reinterpret_cast<PA_Unichar *>(0x1234);
            poisonedOutput.uValue.fString.fLength = 100;
            require(!ob_get_a(obj, L"key", &output), "failed string getter must report failure");
            require(output == CUTF8String(reinterpret_cast<const uint8_t *>("unchanged")), "failed getter preserves output");
            break;
        case eVK_Boolean:
            PA_SetBooleanVariable(&poisonedOutput, true);
            require(!ob_get_b(obj, L"key"), "failed boolean getter must not read output");
            break;
        case eVK_Real:
            PA_SetRealVariable(&poisonedOutput, 99.0);
            require(ob_get_n(obj, L"key") == 0, "failed numeric getter must not read output");
            break;
        case eVK_Object:
            PA_SetObjectVariable(&poisonedOutput, reinterpret_cast<void *>(0x1234));
            require(!ob_get_o(obj, L"key"), "failed object getter must not adopt output");
            break;
        case eVK_Collection:
            PA_SetCollectionVariable(&poisonedOutput, reinterpret_cast<void *>(0x1234));
            require(!ob_get_c(obj, L"key"), "failed collection getter must not adopt output");
            break;
    }
    failGetter = false;
    PA_DisposeObject(obj);
    balanced();
}
static void testStringify(bool failHandle) {
    auto obj = newRef();
    for(int mode = 0; mode != 3; ++mode) {
        CUTF8String output(reinterpret_cast<const uint8_t *>("unchanged"));
        stringifyMode = mode;
        if(failHandle) failHandleAfter = 1; // OB Copy succeeds, next command handle fails.
        ob_stringify(obj, &output);
        CUTF8String expected(reinterpret_cast<const uint8_t *>(
            mode || failHandle ? "unchanged" : "{\"x\":\"\xe6\x97\xa5\xf0\x9f\x98\x80\"}"));
        require(output == expected, "stringify exact result/failure preservation");
        require(refs.size() == 1 && reference(obj)->owners == 1, "stringify temporary references");
    }
    PA_DisposeObject(obj);
    balanced();
}
static void testArrays() {
    PA_Variable array = PA_CreateVariable(eVK_ArrayUnicode);
    PA_ResizeArray(&array, 4);
    const Text expected[] = {text(u"zero"), text(u"ASCII"), text(u"\u65e5"),
                             text(u"\U0001f600"), text(u"")};
    for(int i = 0; i <= 4; ++i) {
        auto value = PA_CreateUnistring(const_cast<PA_Unichar *>(expected[i].c_str()));
        PA_SetStringInArray(array, i, &value);
    }
    ARRAY_TEXT copy;
    BytePtr args[] = {reinterpret_cast<BytePtr>(&array)};
    copy.fromParamAtIndex(args, 1);
    PA_ClearVariable(&array);
    array = PA_CreateVariable(eVK_Undefined);
    copy.toParamAtIndex(args, 1);
    for(int repeat = 0; repeat != 3; ++repeat) {
        for(int i = 0; i <= 4; ++i)
            require(readString(PA_GetStringInArray(array, i)) == expected[i], "independent copied array value");
        copy.toParamAtIndex(args, 1);
    }
    PA_ResizeArray(&array, 1);
    require(readString(PA_GetStringInArray(array, 1)) == expected[1], "shrink surviving owner");
    PA_ClearVariable(&array);
    PA_Variable wrong = PA_CreateVariable(eVK_Longint);
    PA_Variable noData{};
    noData.fType = eVK_ArrayUnicode;
    auto incoming = PA_CreateUnistring(const_cast<PA_Unichar *>(expected[1].c_str()));
    PA_SetStringInArray(wrong, 0, &incoming);
    PA_SetStringInArray(noData, 0, &incoming);
    array = PA_CreateVariable(eVK_ArrayUnicode);
    PA_SetStringInArray(array, -1, &incoming);
    PA_SetStringInArray(array, 1, &incoming);
    PA_SetStringInArray(array, 0, nullptr);
    require(readString(incoming) == expected[1], "rejected transfer retains caller ownership");
    PA_DisposeUnistring(&incoming);
    PA_ClearVariable(&array);
    balanced();
}
static void testArrayRejection(bool allocationFailure) {
    PA_Variable array{};
    array.fType = allocationFailure ? eVK_Undefined : eVK_ArrayUnicode;
    PA_Variable original = array;
    BytePtr args[] = {reinterpret_cast<BytePtr>(&array)};
    ARRAY_TEXT output;
    output.appendUTF16String(text(u"zero").c_str());
    output.appendUTF16String(text(u"value \u65e5\U0001f600").c_str());
    if(allocationFailure) failHandleAfter = 0;
    output.toParamAtIndex(args, 1);
    require(std::memcmp(&array, &original, sizeof(array)) == 0,
            "rejected output must preserve original parameter");
    balanced();
}
static void testScalarContracts() {
    for(const char16_t *fixture : {u"ASCII", u"\u65e5", u"\U0001f600", u""}) {
        Text expected = text(fixture);
        auto source = makeString(expected);
        PA_Variable variable = PA_CreateVariable(eVK_Undefined);
        PA_SetStringVariable(&variable, &source);
        require(variable.uValue.fString.fString == source.fString, "scalar setter shallow alias");
        auto borrowed = PA_GetStringVariable(variable);
        C_TEXT copy;
        copy.setUTF16String(&borrowed);
        PA_ClearVariable(&variable);
        require(Text(copy.getUTF16StringPtr(), copy.getUTF16Length()) == expected,
                "borrowed scalar copied before owner cleanup");
        auto destination = makeString(text(u"replaced"));
        PA_Unistring *result = &destination;
        PluginBlock params{};
        params.fResult = &result;
        PA_ReturnString(&params, const_cast<PA_Unichar *>(copy.getUTF16StringPtr()));
        require(readString(destination) == expected, "return content setter exact UTF-16");
        copy.setUTF16String(text(u"changed").c_str(), 7);
        require(readString(destination) == expected, "return output independent of input buffer");
        PA_DisposeUnistring(&destination);
    }
    balanced();
}
static void testDispatcher() {
    PackInitBlock init{};
    init.fCall4Dex = engine;
    FourDPackex(kInitPlugin, &init, nullptr, nullptr);
    require(permissionCalls == 3, "startup must use only AppleEvent stubs");
    require(init.fSupportedVersion == 0x1400, "actual exported entry initialization");
    PA_Unistring path = makeString(text(u"Audit:synthetic"));
    PA_Unistring value = makeString(text(u"Comment \u65e5\U0001f600"));
    PA_long32 number = 1, result = -1;
    BytePtr args[] = {reinterpret_cast<BytePtr>(&path), reinterpret_cast<BytePtr>(&value)};
    for(int selector : {1, 2, 8, 9, 10, 11, 12}) {
        FourDPackex(selector, args, nullptr, &result);
        require(result == 1, "stubbed Finder dispatcher result");
        if(selector == 2) require(readString(value) == text(u"Comment \u65e5\U0001f600"), "comment output");
        if(selector == 8) require(readString(value) == text(u"Name \u65e5\U0001f600"), "display name output");
        if(selector == 9) require(readString(value) == text(u"Description \u65e5\U0001f600"), "description output");
        if(selector == 10) require(readString(value) == text(u"Kind \u65e5\U0001f600"), "kind output");
    }
    args[1] = reinterpret_cast<BytePtr>(&number);
    for(int selector : {3, 4, 5, 6}) {
        FourDPackex(selector, args, nullptr, &result);
        require(result == 1, "stubbed scalar dispatcher result");
    }
    PA_DisposeUnistring(&path);
    PA_DisposeUnistring(&value);
    require(applicationCalls == 11 && revealCalls == 1 && deleteCalls == 1,
            "all Finder operations must stay in stubs");
    [fixtureComment release];
    fixtureComment = nil;
    PA_Variable array = PA_CreateVariable(eVK_ArrayUnicode);
    PA_ResizeArray(&array, 2);
    Text values[] = {text(u""), text(u"File 11"), text(u"File 2")};
    for(int i = 0; i != 3; ++i) {
        auto str = makeString(values[i]);
        PA_SetStringInArray(array, i, &str);
    }
    args[0] = reinterpret_cast<BytePtr>(&array);
    FourDPackex(7, args, nullptr, nullptr);
    require(readString(PA_GetStringInArray(array, 1)) == text(u"File 2"), "actual sort dispatcher");
    require(readString(PA_GetStringInArray(array, 2)) == text(u"File 11"), "numeric Finder ordering");
    PA_ClearVariable(&array);
    balanced();
}

int main(int argc, char **argv) {
    @autoreleasepool {
        try {
            require(argc == 3, "usage: ownership CASE allocated|null");
            gCall4D = engine;
            nullEmpty = std::string(argv[2]) == "null";
            std::map<std::string, std::function<void()>> tests = {
                {"setters-empty-owner", testSetters}, {"picture-empty-owner", testPicture},
                {"getter-owned-results", testGetters}, {"getter-owning-handoffs", testHandoffs},
                {"failed-getter-string", [] { testFailedGetter(eVK_Unistring); }},
                {"failed-getter-boolean", [] { testFailedGetter(eVK_Boolean); }},
                {"failed-getter-number", [] { testFailedGetter(eVK_Real); }},
                {"failed-getter-object", [] { testFailedGetter(eVK_Object); }},
                {"failed-getter-collection", [] { testFailedGetter(eVK_Collection); }},
                {"stringify-returns", [] { testStringify(false); }},
                {"stringify-raw-zero-sentinel", [] { testStringify(true); }},
                {"array-copy-transfer", testArrays},
                {"array-rejected-destination", [] { testArrayRejection(false); }},
                {"array-allocation-rejection", [] { testArrayRejection(true); }},
                {"scalar-copy-return", testScalarContracts},
                {"stubbed-exported-dispatcher", testDispatcher}
            };
            tests.at(argv[1])();
            std::cout << "PASS " << argv[1] << " " << argv[2] << "\n";
            return 0;
        } catch(const std::exception &error) {
            std::cerr << "FAIL " << argv[1] << ": " << error.what() << "\n";
            return 1;
        }
    }
}
