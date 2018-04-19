#!/usr/bin/env python
import struct


class MBus:
    """
    See documentation for more info on Mbus. The code tries to follow the same 
    naming convention as the official documentation
    """

    # TODO: Implement use of secondary addresses
    # TODO: Implement use of SND_UD to set data in the device.

    def __init__(self):
        self.start_byte_short_frame = b'\x10'
        self.start_byte_long_frame = b'\x68'
        self.stop_byte = b'\x16'
        self.single_character_frame = b'\xe5'

    def generate_short_frame(self, c_field, a_field):
        # TODO: check so c_field and a_fields are bytes
        data = c_field + a_field
        checksum = generate_mbus_checksum_byte(data)
        frame = self.start_byte_short_frame + data + checksum + self.stop_byte

        return frame

    def generate_long_frame(self, c_field, a_field, ci_field, user_data):

        total_data = c_field + a_field + user_data
        length_field = byte_from_int(len(total_data))
        checksum = generate_mbus_checksum_byte(total_data)

        frame = self.start_byte_long_frame + length_field + length_field + \
                self.start_byte_long_frame + total_data + checksum + self.stop_byte

        return frame

    def generate_snd_nke_telegram(self, address):
        """
        Init of Slave
        c_field = 0x40
        telegram = short frame

        :param address:
        :return:
        """
        c_field = b'\x40'
        # TODO Validate address to byte
        telegram = self.generate_short_frame(c_field, address)

        return telegram

    def generate_req_ud2_telegram(self, address):

        c_field = b'\x7b'
        # TODO: Figure out C_field functionality, when 7b and when 5b??
        # TODO Validate address to byte
        telegram = self.generate_short_frame(c_field, address)

        return telegram

    def decode_telegram(self, telegram):
        if (telegram[0] != telegram[3]) | (telegram[1] != telegram[2]):
            raise IOError('Start bytes or length bytes is not the same!')

        c_field = telegram[4]
        ci_field = telegram[6]
        total_data = telegram[4:-2]
        checksum = telegram[-2]

        if not control_mbus_checksum(total_data, checksum):
            raise IOError('Checksum Error!')

        if c_field == 0x08 or c_field == 0x18:

            if ci_field == 0x72 or ci_field == 0x76:

                data = self.decode_rsp_ud_variable_data(total_data)

            else:
                raise IOError('CI Field is not recognised')

        else:
            raise IOError('C Field is not recognised')

        return data

    def decode_rsp_ud_variable_data(self, total_data):

        c_field = total_data[0]
        a_field = total_data[1]
        ci_field = total_data[2]
        mbus_interface_identification_number = total_data[3:6]
        manufacturers_number = total_data[7:8]
        version_number_mbus_interface_firmware = total_data[9]
        medium = total_data[10]
        access_number = total_data[11]
        mbus_interface_status = total_data[12]
        signature = total_data[13:14]

        read_out_data = total_data[15:-2]

        more_data_indicator = total_data[-1]  # might not be correct use!

        decoded_read_out_data = self.decode_read_out_data(read_out_data)

        # TODO: There is manufacturer_specific data in the end. after 0x0f. 
        # How to find!!??

        return decoded_read_out_data

    def decode_read_out_data(self, read_out_data):

        data_list = []

        while True:
            counter = 0
            dib_read = False  # Data information block
            vib_read = False  # Value information block
            dib = []
            vib = []

            while (dib_read is False) and (vib_read is False):
                byte_ = read_out_data[counter]
                dib.append(byte_)
                counter += 1
                if not extension_bit_set(byte_):
                    dib_read = True
                    break

            dib_dict = decode_dib(dib)

            if dib_dict['data_format'] == 'Special Function':
                if dib_dict[
                    'Function'] == 'Start of manufacturer_specific data':
                    manufacturer_data = {'description': 'Manufacturer Data',
                                         'Value': read_out_data[
                                                  counter:].decode(),
                                         'unit': 'No unit',
                                         'Value Type': 'No type',
                                         'Tariff': 'No tariff',
                                         'DIB unit': 'No unit',
                                         'Storage Number': 'No storage number'}
                    data_list.append(manufacturer_data)
                    break
                else:
                    raise NotImplementedError(
                        'Have not implemented all special functions')

            while (dib_read is True) and (vib_read is False):
                byte_ = read_out_data[counter]
                vib.append(byte_)
                counter += 1
                if not extension_bit_set(byte_):
                    vib_read = True
                    break

            vib_dict = decode_vib(vib)

            data_length = dib_dict['data_length']

            # Check if there is a proper number on data_length, or else do special stuff.
            if isinstance(data_length, int):
                data = read_out_data[counter:(counter + data_length)]
            else:
                # there is 2 special case.
                # Selection for Readout, no idea on what this is
                if dib_dict['data_format'] == 'Selection of Readout':
                    # TODO: Implement Selection of readout data_format
                    raise NotImplementedError(
                        'Selection of readout data_format not implemented')

                # Variable length
                if dib_dict['data_format'] == 'Variable Length':
                    # TODO: Implement Variable lenght data_format
                    raise NotImplementedError(
                        'variable Length data_format not implemented')
                else:
                    raise ValueError(
                        'data_format in dib_dict contains wrong value: ' +
                        dib_dict['data_format'])

            counter += data_length

            data_dict = decode_data(data, dib_dict, vib_dict)

            data_list.append(data_dict)

            read_out_data = read_out_data[counter:]

        return data_list


def decode_dib(dib):
    dif = dib[0]
    if len(dib) > 1:
        dife = dib[1:]
    else:
        dife = []

    unit = 0
    tariff = 0

    # Check for special functions
    if dif in [0x0f, 0x1f, 0x2f, 0x7f]:
        return {'data_format': 'Special Function',
                'Function': decode_special_functions(dif),

                }

    # Check DIF
    # get lsb of storage number
    storage_number = (dif & 0x40) >> 6
    # get function field
    function_field = (dif & 0x30) >> 4
    # get data field
    data_field = (dif & 0x0f)

    # Check DIFEs
    if len(dife) > 0:
        iteration = 0
        for byte in dife:
            # get unit bit
            unit_bit = byte & 0x40
            unit += (unit_bit << iteration)
            # get tariff bits
            tariff_bits = (byte & 0x30) >> 4
            tariff += (tariff_bits << (iteration * 2))
            # get storage number bits
            storage_number_bits = byte & 0x0f
            storage_number += (storage_number_bits << ((iteration * 4) + 1))
            iteration += 1

    data_description, data_length = decode_dif_data_field(data_field)
    dib_dict = {'data_format': data_description,
                'data_length': data_length,
                'Value Type': decode_dif_function_field(function_field),
                'unit': unit,
                'Tariff': tariff,
                'Storage Number': storage_number}

    return dib_dict


def decode_dif_data_field(data_field):
    """
    Returns the data description and the number of bytes the data is made up of
    Will return false if data_length cannot be predetermined.
    :param data_field:
    :return data_description, data_length:
    """
    if data_field == 0:
        return 'No Data', 0
    elif data_field == 1:
        return '8 Bit Integer', 1
    elif data_field == 2:
        return '16 Bit Integer', 2
    elif data_field == 3:
        return '24 Bit Integer', 3
    elif data_field == 4:
        return '32 Bit Integer', 4
    elif data_field == 5:
        return '32 Bit Real', 4
    elif data_field == 6:
        return '48 Bit Integer', 6
    elif data_field == 7:
        return '64 Bit Integer', 7
    elif data_field == 8:
        return 'Selection for Readout', False
    elif data_field == 9:
        return '2 digit BCD', 1
    elif data_field == 10:
        return '4 digit BCD', 2
    elif data_field == 11:
        return '6 digit BCD', 3
    elif data_field == 12:
        return '8 digit BCD', 4
    elif data_field == 13:
        return 'Variable Length', False
    elif data_field == 14:
        return '12 digit BCD', 6
    elif data_field == 15:
        return 'Special Functions', 1
    # TODO: implement special functions check.
    else:
        raise ValueError(f'Data in data_field is not within specified range. '
                         f'0-15 is allowed. Data used: {data_field}')


def decode_dif_function_field(function_field):
    if function_field == 0:
        return 'Instantaneous'
    elif function_field == 1:
        return 'Maximum'
    elif function_field == 2:
        return 'Minimum'
    elif function_field == 3:
        return 'Value during error state'
    else:
        raise ValueError('Data in function field is not within specified range.'
                         ' 0-3 is allowed. Data used: {function_field}')


def decode_vib(vib):
    vif = vib[0]
    if len(vib) > 1:
        vife = vib[1:]
        raise NotImplementedError('Have not implemented the interpretation of '
                                  'VIFEs')
    else:
        vife = 0
    unit_and_multiplier = vif & 0x7f
    # TODO: Implement interpretation of VIFEs
    vib_dict = decode_vif(unit_and_multiplier)

    return vib_dict


def decode_vif(vif):
    # TODO: Check for valid number before processing.

    vif_reference_dict = {
        0: {'description': 'energy', 'unit': 'Wh', 'multiplier': 0.001},
        1: {'description': 'energy', 'unit': 'Wh', 'multiplier': 0.01},
        2: {'description': 'energy', 'unit': 'Wh', 'multiplier': 0.1},
        3: {'description': 'energy', 'unit': 'Wh', 'multiplier': 1},
        4: {'description': 'energy', 'unit': 'Wh', 'multiplier': 10},
        5: {'description': 'energy', 'unit': 'Wh', 'multiplier': 100},
        6: {'description': 'energy', 'unit': 'Wh', 'multiplier': 1000},
        7: {'description': 'energy', 'unit': 'Wh', 'multiplier': 10000},
        8: {'description': 'energy', 'unit': 'kJ', 'multiplier': 0.001},
        9: {'description': 'energy', 'unit': 'kJ', 'multiplier': 0.01},
        10: {'description': 'energy', 'unit': 'kJ', 'multiplier': 0.1},
        11: {'description': 'energy', 'unit': 'kJ', 'multiplier': 1},
        12: {'description': 'energy', 'unit': 'kJ', 'multiplier': 10},
        13: {'description': 'energy', 'unit': 'kJ', 'multiplier': 100},
        14: {'description': 'energy', 'unit': 'kJ', 'multiplier': 1000},
        15: {'description': 'energy', 'unit': 'kJ', 'multiplier': 10000},
        16: {'description': 'volume', 'unit': 'l', 'multiplier': 0.001},
        17: {'description': 'volume', 'unit': 'l', 'multiplier': 0.01},
        18: {'description': 'volume', 'unit': 'l', 'multiplier': 0.1},
        19: {'description': 'volume', 'unit': 'l', 'multiplier': 1},
        20: {'description': 'volume', 'unit': 'l', 'multiplier': 10},
        21: {'description': 'volume', 'unit': 'l', 'multiplier': 100},
        22: {'description': 'volume', 'unit': 'l', 'multiplier': 1000},
        23: {'description': 'volume', 'unit': 'l', 'multiplier': 10000},
        24: {'description': 'mass', 'unit': 'kg', 'multiplier': 0.001},
        25: {'description': 'mass', 'unit': 'kg', 'multiplier': 0.01},
        26: {'description': 'mass', 'unit': 'kg', 'multiplier': 0.1},
        27: {'description': 'mass', 'unit': 'kg', 'multiplier': 1},
        28: {'description': 'mass', 'unit': 'kg', 'multiplier': 10},
        29: {'description': 'mass', 'unit': 'kg', 'multiplier': 100},
        30: {'description': 'mass', 'unit': 'kg', 'multiplier': 1000},
        31: {'description': 'mass', 'unit': 'kg', 'multiplier': 10000},
        32: {'description': 'on_time', 'unit': 'seconds', 'multiplier': 1},
        33: {'description': 'on_time', 'unit': 'minutes', 'multiplier': 1},
        34: {'description': 'on_time', 'unit': 'hours', 'multiplier': 1},
        35: {'description': 'on_time', 'unit': 'days', 'multiplier': 1},
        36: {'description': 'operating_time', 'unit': 'seconds',
             'multiplier': 1},
        37: {'description': 'operating_time', 'unit': 'minutes',
             'multiplier': 1},
        38: {'description': 'operating_time', 'unit': 'hours', 'multiplier': 1},
        39: {'description': 'operating_time', 'unit': 'days', 'multiplier': 1},
        40: {'description': 'power', 'unit': 'W', 'multiplier': 0.001},
        41: {'description': 'power', 'unit': 'W', 'multiplier': 0.01},
        42: {'description': 'power', 'unit': 'W', 'multiplier': 0.1},
        43: {'description': 'power', 'unit': 'W', 'multiplier': 1},
        44: {'description': 'power', 'unit': 'W', 'multiplier': 10},
        45: {'description': 'power', 'unit': 'W', 'multiplier': 100},
        46: {'description': 'power', 'unit': 'W', 'multiplier': 1000},
        47: {'description': 'power', 'unit': 'W', 'multiplier': 10000},
        48: {'description': 'power', 'unit': 'kJ/h', 'multiplier': 0.001},
        49: {'description': 'power', 'unit': 'kJ/h', 'multiplier': 0.01},
        50: {'description': 'power', 'unit': 'kJ/h', 'multiplier': 0.1},
        51: {'description': 'power', 'unit': 'kJ/h', 'multiplier': 1},
        52: {'description': 'power', 'unit': 'kJ/h', 'multiplier': 10},
        53: {'description': 'power', 'unit': 'kJ/h', 'multiplier': 100},
        54: {'description': 'power', 'unit': 'kJ/h', 'multiplier': 1000},
        55: {'description': 'power', 'unit': 'kJ/h', 'multiplier': 10000},
        56: {'description': 'volume_flow', 'unit': 'l/h', 'multiplier': 0.001},
        57: {'description': 'volume_flow', 'unit': 'l/h', 'multiplier': 0.01},
        58: {'description': 'volume_flow', 'unit': 'l/h', 'multiplier': 0.1},
        59: {'description': 'volume_flow', 'unit': 'l/h', 'multiplier': 1},
        60: {'description': 'volume_flow', 'unit': 'l/h', 'multiplier': 10},
        61: {'description': 'volume_flow', 'unit': 'l/h', 'multiplier': 100},
        62: {'description': 'volume_flow', 'unit': 'l/h', 'multiplier': 1000},
        63: {'description': 'volume_flow', 'unit': 'l/h', 'multiplier': 10000},
        64: {'description': 'volume_flow', 'unit': 'l/min',
             'multiplier': 0.0001},
        65: {'description': 'volume_flow', 'unit': 'l/min',
             'multiplier': 0.001},
        66: {'description': 'volume_flow', 'unit': 'l/min', 'multiplier': 0.01},
        67: {'description': 'volume_flow', 'unit': 'l/min', 'multiplier': 0.1},
        68: {'description': 'volume_flow', 'unit': 'l/min', 'multiplier': 1},
        69: {'description': 'volume_flow', 'unit': 'l/min', 'multiplier': 10},
        70: {'description': 'volume_flow', 'unit': 'l/min', 'multiplier': 100},
        71: {'description': 'volume_flow', 'unit': 'l/min', 'multiplier': 1000},
        72: {'description': 'volume_flow', 'unit': 'ml/s', 'multiplier': 0.001},
        73: {'description': 'volume_flow', 'unit': 'ml/s', 'multiplier': 0.01},
        74: {'description': 'volume_flow', 'unit': 'ml/s', 'multiplier': 0.1},
        75: {'description': 'volume_flow', 'unit': 'ml/s', 'multiplier': 1},
        76: {'description': 'volume_flow', 'unit': 'ml/s', 'multiplier': 10},
        77: {'description': 'volume_flow', 'unit': 'ml/s', 'multiplier': 100},
        78: {'description': 'volume_flow', 'unit': 'ml/s', 'multiplier': 1000},
        79: {'description': 'volume_flow', 'unit': 'ml/s', 'multiplier': 10000},
        80: {'description': 'mass_flow', 'unit': 'kg/h', 'multiplier': 0.001},
        81: {'description': 'mass_flow', 'unit': 'kg/h', 'multiplier': 0.01},
        82: {'description': 'mass_flow', 'unit': 'kg/h', 'multiplier': 0.1},
        83: {'description': 'mass_flow', 'unit': 'kg/h', 'multiplier': 1},
        84: {'description': 'mass_flow', 'unit': 'kg/h', 'multiplier': 10},
        85: {'description': 'mass_flow', 'unit': 'kg/h', 'multiplier': 100},
        86: {'description': 'mass_flow', 'unit': 'kg/h', 'multiplier': 1000},
        87: {'description': 'mass_flow', 'unit': 'kg/h', 'multiplier': 10000},
        88: {'description': 'flow_temperature', 'unit': 'degC',
             'multiplier': 0.001},
        89: {'description': 'flow_temperature', 'unit': 'degC',
             'multiplier': 0.01},
        90: {'description': 'flow_temperature', 'unit': 'degC',
             'multiplier': 0.1},
        91: {'description': 'flow_temperature', 'unit': 'degC',
             'multiplier': 1},
        92: {'description': 'return_temperature', 'unit': 'degC',
             'multiplier': 0.001},
        93: {'description': 'return_temperature', 'unit': 'degC',
             'multiplier': 0.01},
        94: {'description': 'return_temperature', 'unit': 'degC',
             'multiplier': 0.1},
        95: {'description': 'return_temperature', 'unit': 'degC',
             'multiplier': 1},
        96: {'description': 'temperature_difference', 'unit': 'mK',
             'multiplier': 1},
        97: {'description': 'temperature_difference', 'unit': 'mK',
             'multiplier': 10},
        98: {'description': 'temperature_difference', 'unit': 'mK',
             'multiplier': 100},
        99: {'description': 'temperature_difference', 'unit': 'mK',
             'multiplier': 1000},
        100: {'description': 'external_temperature', 'unit': 'degC',
              'multiplier': 0.001},
        101: {'description': 'external_temperature', 'unit': 'degC',
              'multiplier': 0.01},
        102: {'description': 'external_temperature', 'unit': 'degC',
              'multiplier': 0.1},
        103: {'description': 'external_temperature', 'unit': 'degC',
              'multiplier': 1},
        104: {'description': 'pressure', 'unit': 'mbar', 'multiplier': 1},
        105: {'description': 'pressure', 'unit': 'mbar', 'multiplier': 10},
        106: {'description': 'pressure', 'unit': 'mbar', 'multiplier': 100},
        107: {'description': 'pressure', 'unit': 'mbar', 'multiplier': 1000},
        108: {'description': 'time_point', 'unit': 'Date, data type G',
              'multiplier': 1},
        109: {'description': 'time_point', 'unit': 'Time+Date, data type F',
              'multiplier': 1},
        110: {'description': 'units_for_h_c_a', 'unit': 'dimensionless',
              'multiplier': 1},
        111: {'description': 'reserved', 'unit': 'None', 'multiplier': 1},
        112: {'description': 'averaging_duration', 'unit': 'seconds',
              'multiplier': 1},
        113: {'description': 'averaging_duration', 'unit': 'minutes',
              'multiplier': 1},
        114: {'description': 'averaging_duration', 'unit': 'hours',
              'multiplier': 1},
        115: {'description': 'averaging_duration', 'unit': 'days',
              'multiplier': 1},
        116: {'description': 'actuality_duration', 'unit': 'seconds',
              'multiplier': 1},
        117: {'description': 'actuality_duration', 'unit': 'minutes',
              'multiplier': 1},
        118: {'description': 'actuality_duration', 'unit': 'hours',
              'multiplier': 1},
        119: {'description': 'actuality_duration', 'unit': 'days',
              'multiplier': 1},
        120: {'description': 'fabrication_number', 'unit': 'None',
              'multiplier': 1},
        121: {'description': 'enhanced_features_available', 'unit': 'None',
              'multiplier': 1},
        122: {'description': 'bus_address', 'unit': 'data type C',
              'multiplier': 1},
        123: {'description': 'extension_if_vif_codes', 'unit': 'None',
              'multiplier': 1},
        # True VIF is given in the first VIFE and is coded using table 8.4.4.b
        124: {'description': 'vif_in_following_string', 'unit': 'None',
              'multiplier': 1},
        # Allows user defineable VIF's (in plain ASCII)
        # Coding the VID in an ASCII-string in combination with the data in an ASCII-string (datafield
        # in DIF = 0b1101 allows the representation of data in a free user defined form
        125: {'description': 'extension_if_vif_codes', 'unit': 'None',
              'multiplier': 1},
        # True VIF is given in the first VIFE and is coded using table 8.4.4.aa7
        126: {'description': 'any_vif', 'unit': 'None', 'multiplier': 1},
        # Used for readout selection of all VIF's (see chapter 6.4.3)
        127: {'description': 'manufacturer_specific', 'unit': 'None',
              'multiplier': 1},
        # VIFE's and data of this block are manufacturer_specific
    }

    decoded_vif = vif_reference_dict[vif]

    if decoded_vif['description'] in ('units_for_h_c_a' or
                                      'extension_if_vif_codes' or
                                      'vif_in_following_string' or
                                      'any_vif' or
                                      'manufacturer_specific'):
        raise NotImplementedError(f'The VIF  {vif} is not implemented')

    return decoded_vif


def decode_data(data, dib_dict, vib_dict):
    if dib_dict['data_format'] == 'No Data':
        raise NotImplementedError(
            'Have not implemented a way to handle No data')
    elif dib_dict['data_format'] == '8 Bit Integer':
        value = decode_8_bit_integer(data) * vib_dict['multiplier']
    elif dib_dict['data_format'] == '16 Bit Integer':
        if vib_dict['description'] == 'time_point':
            value = decode_time(data)
        else:
            value = decode_16_bit_integer(data) * vib_dict['multiplier']
    elif dib_dict['data_format'] == '24 Bit Integer':
        value = decode_24_bit_integer(data) * vib_dict['multiplier']
    elif dib_dict['data_format'] == '32 Bit Integer':
        if vib_dict['description'] == 'time_point':
            value = decode_time(data)
        else:
            value = decode_32_bit_integer(data) * vib_dict['multiplier']
    elif dib_dict['data_format'] == '32 Bit Real':  # floating point
        value = decode_32_bit_float(data) * vib_dict['multiplier']
    elif dib_dict['data_format'] == '48 Bit Integer':
        value = decode_48_bit_integer(data) * vib_dict['multiplier']
    elif dib_dict['data_format'] == '64 Bit Integer':
        value = decode_64_bit_integer(data) * vib_dict['multiplier']
    elif dib_dict['data_format'] == '2 digit BCD':
        value = decode_bcd(data, 2) * vib_dict['multiplier']
    elif dib_dict['data_format'] == '4 digit BCD':
        value = decode_bcd(data, 4) * vib_dict['multiplier']
    elif dib_dict['data_format'] == '6 digit BCD':
        value = decode_bcd(data, 6) * vib_dict['multiplier']
    elif dib_dict['data_format'] == '8 digit BCD':
        value = decode_bcd(data, 8) * vib_dict['multiplier']
    elif dib_dict['data_format'] == '12 digit BCD':
        value = decode_bcd(data, 12) * vib_dict['multiplier']
    elif dib_dict['data_format'] == 'Special Functions':
        return {'description': decode_special_functions(data)}
    else:
        raise ValueError(
            'data_format in dib_dict is not valid for interpretation: ' +
            dib_dict['data_format'])

    data_dict = {'description': vib_dict['description'],
                 'Value': value,
                 'unit': vib_dict['unit'],
                 'Value Type': dib_dict['Value Type'],
                 'Tariff': dib_dict['Tariff'],
                 'DIB unit': dib_dict['unit'],
                 'Storage Number': dib_dict['Storage Number']
                 }

    return data_dict


# TODO: replace all decode integer with int.from_bytes(xxx, 'big')
def decode_8_bit_integer(data):
    # TODO: Make 1 function to cover all integer decoding.
    if len(data) != 1:
        raise ValueError('Not correct data_length for decoding 8 bit integer')
    value = int(data)

    return value


def decode_16_bit_integer(data):
    if len(data) != 2:
        raise ValueError('Not correct data_length for decoding 16 bit integer')
    value = 0
    value += data[1]
    value += data[0] << 8

    return int(value)


def decode_24_bit_integer(data):
    if len(data) != 3:
        raise ValueError('Not correct data_length for decoding 24 bit integer')
    value = 0
    value += data[2]
    value += data[1] << 8
    value += data[0] << 16

    return int(value)


def decode_32_bit_integer(data):
    if len(data) != 4:
        raise ValueError('Not correct data_length for decoding 32 bit integer')
    value = 0
    value += data[3]
    value += data[2] << 8
    value += data[1] << 16
    value += data[0] << 24

    return int(value)


def decode_48_bit_integer(data):
    if len(data) != 6:
        raise ValueError('Not correct data_length for decoding 48 bit integer')
    value = 0
    value += data[5]
    value += data[4] << 1 * 8
    value += data[3] << 2 * 8
    value += data[2] << 3 * 8
    value += data[1] << 4 * 8
    value += data[0] << 5 * 8

    return int(value)


def decode_64_bit_integer(data):
    if len(data) != 8:
        raise ValueError('Not correct data_length for decoding 64 bit integer')
    value = 0
    value += data[7]
    value += data[6] << 1 * 8
    value += data[5] << 2 * 8
    value += data[4] << 3 * 8
    value += data[3] << 4 * 8
    value += data[2] << 5 * 8
    value += data[1] << 6 * 8
    value += data[0] << 7 * 8

    return int(value)


def decode_bcd(data, digits):
    if len(data) != digits / 2:
        raise ValueError('The data lenght and number of digits does not match')
    value = 0
    count = 0
    for byte_ in data:
        value += (byte_ & 0x0f) * (10 ** count)
        count += 1
        value += ((byte_ & 0xf0) >> 4) * (10 ** count)
        count += 1

    return int(value)


def decode_32_bit_float(data):
    value = struct.unpack('f', data)  # converts bytes to float
    return value


def decode_time(data):
    if len(data) == 4:
        if data[0] & 8 == 1:
            return 'Invalid Time'
        else:
            min = data[0] & 0x3F
            hour = data[1] & 0x1F
            mday = data[2] & 0x1F
            mon = (data[3] & 0x0F)
            year = ((data[2] & 0xE0) >> 5) | ((data[3] & 0xF0) >> 1)
            # is_dayligt_saving_time = (data[1] & 0x80) >> 7  # day saving time
            # TODO: include daylight savings time

        time_string = str(year) + ':' + str(mon) + ':' + str(mday) + ' ' + str(
            hour) + ':' + str(min)

    elif len(data) == 2:
        mday = data[0] & 0x1F
        mon = (data[1] & 0x0F) - 1
        year = ((data[0] & 0xE0) >> 5) | ((data[1] & 0xF0) >> 1)

        time_string = str(year) + ':' + str(mon) + ':' + str(mday)
    else:
        raise ValueError('data_length for time decoding must be 4 or 2')

    return time_string


def decode_special_functions(data):
    if data == 0x0f:
        func = 'Start of manufacturer_specific data'
    elif data == 0x1f:
        # func = 'Start of manufacturer_specific data: More data in following telegram'
        raise NotImplementedError('Have not implemented multiple telegrams')
    elif data == 0x2f:
        # func = 'Idle Filler (not to be implemented), following byte = DIF'
        raise NotImplementedError('Have not implemented handing of idle filler')
    elif data == 0x7f:
        # func = 'Global readout request'
        raise NotImplementedError(
            'Have not implemented handling of global readout request in special functions from DIF')
    else:
        raise ValueError(
            'Value error in decode special functions. Data = ' + str(data))

    return func


def extension_bit_set(byte):
    extension_bit = byte & 0x80
    if extension_bit > 0:
        return True
    else:
        return False


def control_mbus_checksum(data, received_checksum_byte):
    is_int = isinstance(received_checksum_byte, int)

    if is_int:
        received_checksum_byte = byte_from_int(received_checksum_byte)

    calculated_checksum_byte = generate_mbus_checksum_byte(data)

    if calculated_checksum_byte == received_checksum_byte:
        return True
    else:
        raise ValueError(
            'Calculated checksum = ' + str(calculated_checksum_byte))


def generate_mbus_checksum_byte(data):
    checksum = 0
    for byte in data:
        checksum += byte
    checksum &= 0xff

    checksum_char = chr(checksum)
    checksum_byte = checksum_char.encode('latin-1')

    return checksum_byte


def byte_from_int(number):
    # TODO Validate that it is only a number that can fit in a single byte. Or that it trunkates or that it generates
    # the correct byte representation of the data!

    char = chr(number)
    char_byte = char.encode('latin-1')
    return char_byte
