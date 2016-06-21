///
/// The objects in this file are used by generated code and should not need to be invoked manually.
///

#import <Foundation/Foundation.h>
#import "StoneSerializers.h"

///
/// Route objects used to encapsulate route-specific information.
///
@interface Route : NSObject

- (nonnull instancetype)init:(NSString * _Nonnull)name namespace_:(NSString * _Nonnull)namespace_ deprecated:(NSNumber * _Nonnull)deprecated resultType:(Class<Serializable> _Nullable)resultType errorType:(Class<Serializable> _Nullable)errorType attrs:(NSDictionary<NSString *, NSString *> * _Nonnull)attrs;

@property (nonatomic) NSString * _Nonnull name;
@property (nonatomic) NSString * _Nonnull namespace_;
@property (nonatomic) NSNumber * _Nonnull deprecated;
@property (nonatomic) Class<Serializable> _Nullable resultType;
@property (nonatomic) Class<Serializable> _Nullable errorType;
@property (nonatomic) NSDictionary<NSString *, NSString *> * _Nonnull attrs;

@end
