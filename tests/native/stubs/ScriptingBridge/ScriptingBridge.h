#pragma once
#import <Foundation/Foundation.h>

// Do not link ScriptingBridge: every application/item interaction is synthetic.
@interface SBObject : NSObject
- (BOOL)exists;
@end

@interface SBElementArray : NSObject
- (id)objectAtLocation:(id)location;
@end

@interface SBApplication : SBObject
+ (id)applicationWithBundleIdentifier:(NSString *)identifier;
- (SBElementArray *)items;
@end
