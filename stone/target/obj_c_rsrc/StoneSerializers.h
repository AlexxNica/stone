///
/// The objects in this file are used by generated code and should not need to be invoked manually.
///

#import <Foundation/Foundation.h>

///
/// Validator functions used by SDK to impose value constraints.
///
@protocol Serializable <NSObject>

+ (NSDictionary * _Nonnull)serialize:(id _Nonnull)obj;

+ (id _Nonnull)deserialize:(NSDictionary * _Nonnull)dict;

@end


@interface StringSerializer : NSObject

+ (NSString * _Nonnull)serialize:(NSString * _Nonnull)value;

+ (NSString * _Nonnull)deserialize:(NSString * _Nonnull)value;

@end


@interface NSNumberSerializer : NSObject

+ (NSNumber * _Nonnull)serialize:(NSNumber * _Nonnull)value;

+ (NSNumber * _Nonnull)deserialize:(NSNumber * _Nonnull)value;

@end


@interface BoolSerializer : NSObject

+ (NSNumber * _Nonnull)serialize:(NSNumber * _Nonnull)value;

+ (NSNumber * _Nonnull)deserialize:(NSNumber * _Nonnull)value;

@end


@interface NSDateSerializer : NSObject

+ (NSString * _Nonnull)serialize:(NSDate * _Nonnull)value dateFormat:(NSString * _Nonnull)dateFormat;

+ (NSDate * _Nonnull)deserialize:(NSString * _Nonnull)value dateFormat:(NSString * _Nonnull)dateFormat;

@end


@interface ArraySerializer : NSObject

+ (NSArray * _Nonnull)serialize:(NSArray * _Nonnull)value withBlock:(id _Nonnull(^_Nonnull)(id _Nonnull obj))withBlock;

+ (NSArray * _Nonnull)deserialize:(NSArray * _Nonnull)jsonData withBlock:(id _Nonnull(^_Nonnull)(id _Nonnull obj))withBlock;

@end
