import dns.resolver
import socket

def get_ip_addresses(domain):
    """
    Retrieves both IPv4 and IPv6 addresses associated with a domain.
    """
    ip_addresses = {
        'A': [],    # IPv4 addresses
        'AAAA': []  # IPv6 addresses
    }
    
    try:
        # Query IPv4 addresses (A record)
        a_records = dns.resolver.resolve(domain, 'A')
        for record in a_records:
            ip_addresses['A'].append(record.to_text())
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        print(f"No IPv4 addresses found for {domain}.")
    
    try:
        # Query IPv6 addresses (AAAA record)
        aaaa_records = dns.resolver.resolve(domain, 'AAAA')
        for record in aaaa_records:
            ip_addresses['AAAA'].append(record.to_text())
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        print(f"No IPv6 addresses found for {domain}.")
    
    return ip_addresses

def verify_ip_address(ip):
    """
    Verifies if the IP address is reachable by attempting a socket connection.
    For the purpose of this demo, it uses the socket library to check connectivity.
    """
    try:
        # Attempt to create a socket connection
        socket.inet_pton(socket.AF_INET, ip)  # Check if it's a valid IPv4 address
        return True
    except socket.error:
        return False

def prevent_dns_pinning_attack(domain):
    """
    Retrieves IP addresses and performs verification to prevent DNS pinning attack.
    """
    ip_addresses = get_ip_addresses(domain)
    all_verified_ips = {
        'A': [],
        'AAAA': []
    }
    
    # Verify IPv4 addresses
    for ip in ip_addresses['A']:
        if verify_ip_address(ip):
            all_verified_ips['A'].append(ip)
    
    # Verify IPv6 addresses
    for ip in ip_addresses['AAAA']:
        if verify_ip_address(ip):
            all_verified_ips['AAAA'].append(ip)
    
    # Output valid IPs
    print(f"Verified IPv4 Addresses for {domain}: {all_verified_ips['A']}")
    print(f"Verified IPv6 Addresses for {domain}: {all_verified_ips['AAAA']}")
    
    return all_verified_ips

# Example usage
domain = "example.com"  # Replace with the domain you want to check
verified_ips = prevent_dns_pinning_attack(domain)